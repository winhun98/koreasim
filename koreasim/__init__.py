"""KoreaSim — Demographically-grounded Korean society simulator.

Simulate how 700M demographically-accurate Korean personas respond to any event,
policy change, or scenario. Powered by Nemotron-Personas-Korea (NVIDIA) + BitNet 1.58-bit.
"""

__version__ = "0.1.0"

from koreasim.persona.schema import KoreanPersona, Reaction
from koreasim.scenario.runner import ScenarioResult, ScenarioRunner

__all__ = [
    "KoreanPersona",
    "Reaction",
    "ScenarioRunner",
    "ScenarioResult",
]
