"""One local llama.cpp process, or an explicitly labeled mock backend."""
from __future__ import annotations

import json
import fcntl
import socket
import subprocess
import time
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .storage import ROOT

MODEL = ROOT / "models/LFM3-1.7B-Q4_K_M.gguf"
BUILD_SERVER = ROOT / "runtime/llama.cpp/build/bin/llama-server"
PREBUILT_SERVER = ROOT / "runtime/llama-b12088/llama-server"
SERVER = BUILD_SERVER if BUILD_SERVER.is_file() else PREBUILT_SERVER
MODEL_ID = "LiquidAI/LFM3-1.7B-GGUF"


class Backend(Protocol):
    def decide(self, prompt: str) -> tuple[str, int]: ...
    def close(self) -> None: ...


class MockBackend:
    """Deterministic test double, never represented as real model output."""
    def decide(self, prompt: str) -> tuple[str, int]:
        obs = json.loads(prompt)
        if obs["observation"]["predator"]:
            objective, target = "FLEE", None
        elif obs["observation"]["food"]:
            objective, target = "FORAGE", obs["observation"]["food"][0]["id"]
        else:
            objective, target = "COHERE", None
        return json.dumps({"objective": objective, "duration": 5, "target_id": target}), 0

    def close(self) -> None:
        pass


class LlamaBackend:
    def __init__(self, port: int | None = None, *, model: Path | None = None,
                 context: int = 2048, max_tokens: int = 96, temperature: float = 0.0):
        model = (model or MODEL).resolve()
        if context not in (2048, 4096, 8192) or not 64 <= max_tokens <= 256 or not 0 <= temperature <= 1:
            raise ValueError("unsupported generation settings")
        self.model_id = model.name
        self.max_tokens, self.temperature = max_tokens, temperature
        if not model.is_relative_to((ROOT / "models").resolve()) or not SERVER.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("model or runtime path escapes project root")
        if not model.is_file():
            raise FileNotFoundError("LFM3 GGUF missing; run scripts/download_model.sh")
        if not SERVER.is_file():
            raise FileNotFoundError("llama-server missing; run scripts/setup.sh --runtime")
        if port is None:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.peak_rss_kib = 0
        lock_path = ROOT / "tmp/model-inference.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if lock_path.is_symlink():
            raise ValueError("model lock cannot be a symlink")
        self.model_lock = lock_path.open("a")
        try:
            fcntl.flock(self.model_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.model_lock.close()
            self.model_lock = None
            raise RuntimeError("Another project process owns the model; stop it before loading another")
        try:
            self.process = subprocess.Popen([str(SERVER), "-m", str(model), "--host", "127.0.0.1",
                                             "--port", str(port), "-c", str(context), "-np", "1", "-t", "4",
                                             "--reasoning", "off", "--no-webui"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except BaseException:
            self.close()
            raise
        try:
            for _ in range(80):
                if self.process.poll() is not None:
                    raise RuntimeError("llama-server exited during startup")
                try:
                    with urlopen(self.url + "/health", timeout=.5) as response:
                        if response.status == 200:
                            self._sample_rss()
                            return
                except HTTPError as exc:
                    exc.close()
                    time.sleep(.25)
                except OSError:
                    time.sleep(.25)
            raise RuntimeError("llama-server startup timed out")
        except BaseException:
            self.close()
            raise

    def decide(self, prompt: str) -> tuple[str, int]:
        observation = json.loads(prompt)["observation"]
        food_ids = [item["id"] for item in observation["food"]]
        neighbor_ids = [item["id"] for item in observation["neighbors"]]
        objectives = ["EXPLORE", "COHERE", "REST"]
        if observation["predator"] is not None: objectives.append("FLEE")
        if food_ids: objectives.append("FORAGE")
        if neighbor_ids: objectives.append("FOLLOW")
        def branch(objective: str) -> dict:
            targets = food_ids if objective == "FORAGE" else neighbor_ids if objective == "FOLLOW" else []
            target_schema = {"type": "string", "enum": targets} if targets else {"type": "null"}
            return {"type": "object", "properties": {
                "objective": {"const": objective},
                "duration": {"type": "integer", "minimum": 1, "maximum": 12},
                "target_id": target_schema},
                "required": ["objective", "duration", "target_id"], "additionalProperties": False}
        schema = {"oneOf": [branch(objective) for objective in objectives]}
        instruction = ("You control one prey fish. Select exactly one objective from the allowed values. "
                       "Use FLEE when predator is observed; use FORAGE with a visible food id when hungry; "
                       "FOLLOW requires a visible prey id. For FORAGE or FOLLOW set target_id to that id. "
                       "For every other objective set target_id to null. Duration is 1 through 12 ticks. "
                       "Reply with a JSON object only. Do not change physical state.")
        payload = {"model": self.model_id, "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": prompt}], "temperature": self.temperature, "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object", "schema": schema},
            "chat_template_kwargs": {"enable_thinking": False}}
        request = Request(self.url + "/v1/chat/completions", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=90) as response:
            data = json.load(response)
        self._sample_rss()
        return data["choices"][0]["message"]["content"], data.get("usage", {}).get("total_tokens", 0)

    def _sample_rss(self) -> None:
        try:
            result = subprocess.run(["ps", "-o", "rss=", "-p", str(self.process.pid)], capture_output=True, text=True, check=False)
        except OSError:
            return
        try:
            self.peak_rss_kib = max(self.peak_rss_kib, int(result.stdout.strip()))
        except ValueError:
            pass

    def close(self) -> None:
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        lock = getattr(self, "model_lock", None)
        if lock is not None and not lock.closed:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        self.model_lock = None

    def __enter__(self) -> "LlamaBackend":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
