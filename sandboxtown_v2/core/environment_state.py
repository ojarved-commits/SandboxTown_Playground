from enum import Enum


class EnvironmentState(str, Enum):
    CALM = "Calm"
    ACTIVE = "Active"
    DENSE = "Dense"
