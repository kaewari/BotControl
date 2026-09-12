"""Task automation modules for Honkai: Star Rail."""
from bot.tasks.base import BaseTask
from bot.tasks.dialogue import DialogueFastSkipTask
from bot.tasks.daily import DailyTask
from bot.tasks.resin import ResinFarmTask
from bot.tasks.simulated_universe import SimulatedUniverseTask

__all__ = ["BaseTask", "DialogueFastSkipTask", "DailyTask", "ResinFarmTask", "SimulatedUniverseTask"]
