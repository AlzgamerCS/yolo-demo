"""Short per-client audio relay buffer; accessed under the engine condition."""

import time
from collections import deque


class ClientAudioBuffer:
    def __init__(self):
        self.owner = None
        self.sample_rate = None
        self.sequence = 0
        self.packets = deque(maxlen=8)

    def clear(self):
        self.owner = None
        self.sample_rate = None
        self.packets.clear()
        self.sequence += 1

    def push(self, payload):
        self.sequence += 1
        self.packets.append((self.sequence, time.monotonic(), payload))
