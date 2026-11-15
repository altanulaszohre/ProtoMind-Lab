# Scientific model (ODD protocol)

This is an engineering agent-based model inspired by, but not calibrated to, empirical fish trajectories. It follows the [ODD protocol](https://pubs.usgs.gov/publication/70209554) (Overview, Design concepts, Details). The equations below describe the implemented discrete-time system; one tick has no claimed physical unit.

## Overview

### Purpose and patterns

The model tests whether locally informed behavioral objectives from a shared frozen language model, and separately retrieved episodic memory, alter survival, food use, polarization, and fragmentation under predator and resource pressure. It is designed to generate falsifiable comparisons, not to reproduce a particular fish species. Expected patterns to inspect are coordinated movement, exposure, capture, depletion, and recovery. The [2002 Couzin model](https://doi.org/10.1006/jtbi.2002.3065) motivates local interaction and group state dependence; [Couzin et al. 2005](https://doi.org/10.1038/nature03236) motivates testing information propagation without global knowledge; [Ioannou et al. 2012](https://pubmed.ncbi.nlm.nih.gov/22903520/) motivates measuring coordinated motion under predation. These papers do not validate this simulator's parameters or outcomes.

### State variables and scales

Global state at tick `t` is `S_t = (P_t, H_t, F_t, M_t, E_t, R_t)`: prey bodies `P`, one optional predator `H`, food locations and energy `F`, per-agent external memories `M`, logged events `E`, and seeded random-stream states `R`. Each prey body has identity, two-dimensional position `x_i`, velocity `v_i`, energy `e_i`, alive status, current objective, target ID, and decision timing. The predator has the same movement constraints but no feeding-energy balance. The world is a bounded rectangle of configurable width and height. Default calibrated population is eight prey and one predator.

An agent receives only `o_i(t) = O_i(S_t)`: its own energy and ID, relative positions of living prey and food within prey sensing radius `r_p`, and predator relative position only if within `r_p`. It receives no global counts, unobserved coordinates, future events, or other agents' memory. The predator pursues only prey within its own radius `r_h`; otherwise it patrols using a seeded heading. This is a partially observable multi-agent dynamical system with `S_{t+1} = T(S_t, a_1(t), …, a_N(t), ξ_t)`, where `ξ_t` is the seed-controlled resource/patrol process. The action space is the discrete set `FORAGE, EXPLORE, COHERE, FOLLOW, FLEE, REST` plus a visible target ID where required and a bounded duration of 1–12 ticks.

### Process overview and scheduling

At each tick, each living prey obtains a local observation. An initial, interval, or change event may trigger one decision, subject to a cooldown except for newly detected threats. Decision output is schema constrained, then validated against current visibility and objective-specific target rules. Invalid output becomes a logged safe fallback. A movement controller maps the objective to a steering vector. Prey are then updated in ascending identity order: each moves, pays energy cost, may consume one nearby food resource, and may starve. This fixed asynchronous order means later prey can react to earlier movement and earlier IDs can claim shared food first. The predator then senses, moves, and may capture one prey. Resources replenish, stochastic spawn is evaluated, and a configured resource shift may occur. Model inference wall time does not enter the tick equations; recorded actions can be replayed without inference.

## Design concepts

- **Basic principles:** Separation, alignment, and cohesion are explicit local steering terms, inspired by collective-motion models. Predator avoidance and food attraction are separate terms. Social strength zero is a collective-interaction ablation.
- **Emergence:** Group polarization, fragmentation, and survival are measured from local interactions; none is hardcoded as a desired outcome.
- **Adaptation and objectives:** LFM3 selects a short-lived objective, not a position or physical state update. Persistent SQLite memories do not update model weights.
- **Learning:** No parameter learning is implemented. Condition C retrieves prior individual records; D retrieves the same namespace after information-scrambling as a negative control.
- **Sensing and interaction:** Prey and predator have finite, independently configurable sensing ranges. Food is consumable by one prey, creating competition.
- **Stochasticity:** Four deterministic streams derive from the seed for initialization, resources, environmental events, and predator patrol. A configurable spawn probability supplies stochastic resource events. Fixed configuration plus validated actions and seed yield deterministic replay.
- **Observation:** The simulator records per-tick survival, mean energy, alignment, cohesion, fragmentation, exposure, new encounters, captures, and food consumption. No simulation agent reads these aggregate metrics.

## Details

### Initialization and input

Prey positions are drawn uniformly from the central 60% of each axis, all with configured initial energy. The predator starts near the top center. Food positions are independently seeded and initially uniform. `configs/calibrated_v1.json` freezes one mechanistically calibrated setting. Four scenarios change predator presence, food scarcity, or a mid-episode resource relocation. No observed animal data are loaded.

### Movement and energy submodels

For a body with desired direction `d`, the requested velocity is `v* = v_max d/||d||`. Acceleration is limited by `||v_{t+1}-v_t|| <= a_max` in free space, speed by `||v_{t+1}|| <= v_max`, and the heading change by `|Δθ| <= θ_max` per tick. Position updates as `x_{t+1} = clamp(x_t + v_{t+1}, world bounds)`. A wall collision sets its outward velocity component to zero; this collision impulse is an explicit exception to the free-space acceleration bound. The prey and predator use the same movement routine with different speed caps.

Local steering combines separation from very near neighbors, mean neighbor velocity (alignment), and displacement toward mean neighbor position (cohesion), multiplied by configurable social strength and objective-specific weight. `FORAGE` adds attraction to a currently visible food target, `FOLLOW` to a visible prey target, `FLEE` adds strong repulsion from a sensed predator, `EXPLORE` adds a fixed directional/centering term, and `REST` requests zero velocity. These weights are engineering choices, not measured fish coefficients.

Prey energy follows `e_i(t+1) = min(e_max, e_i(t) - m - c ||v_i(t+1)|| + q_i(t))`, where `q_i` is food energy when a resource is consumed and zero otherwise. Death occurs at `e_i <= 0`. There is no reproduction or injury model. Food is point-like; at most one resource per prey per tick is consumed within interaction radius. One resource is replenished at configured intervals up to capacity; optional stochastic spawns use the environmental RNG. A change scenario relocates remaining food in the second half of the episode.

The predator selects the nearest prey **within predator perception**, else patrols using its seeded heading. Capture occurs when distance is at most capture radius after movement, with at most one capture per tick. An encounter is a prey's entry into predator perception; exposure is measured in prey-ticks inside that range. Predator hunger, handling time, and visual occlusion are omitted.

For C and D, each `M_i(t+1)` appends that prey's observed state, decisions, and experienced events, removes expired rows, and retains at most the configured capacity. Retrieval selects at most four recent/relevant rows. B supplies an empty memory field. D scrambles values in retrieved rows but stores its own history under the same individual namespace. None of these operations changes model parameters.
