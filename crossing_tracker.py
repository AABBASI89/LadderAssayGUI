# crossing_tracker.py

from config import FULL_CROSSINGS_PER_DIRECTION

FULL = "FULL"
HALF = "HALF"


class CrossingTracker:
    """
    Trial sequencing and crossing bookkeeping (no Qt, no hardware).

    Rules:

    - The first beam broken while armed starts the first trial.
    - While a trial is recording, a break of either beam stops it.
    - The beam that stopped a trial is the only beam that can start the
      next one (breaks of the other beam are ignored in between).
    - Start beam != stop beam  -> FULL crossing (direction 1->2 or 2->1)
    - Start beam == stop beam  -> HALF crossing
    - Only FULL crossings count, up to `per_direction` for each
      direction. The session is complete when both quotas are met.
    """

    def __init__(self, per_direction=FULL_CROSSINGS_PER_DIRECTION):

        self.per_direction = per_direction

        # Beam (1 or 2) that may start the next trial; None = either
        self.next_start_beam = None

        self.start_beam = None

        self.full_counts = {(1, 2): 0, (2, 1): 0}

        self.half_count = 0

    # --------------------------------------------------

    def can_start(self, beam):
        """True if a break of `beam` may start a trial."""

        if self.complete:
            return False

        return self.next_start_beam in (None, beam)

    def start(self, beam):

        self.start_beam = beam

    def stop(self, beam):
        """
        Ends the current trial with a break of `beam`.

        Returns a dict describing the crossing:
        type, direction, start_beam, stop_beam, counted.
        """

        start_beam = self.start_beam

        self.start_beam = None

        # This beam starts the next trial
        self.next_start_beam = beam

        if start_beam == beam:

            self.half_count += 1

            return {
                "type": HALF,
                "direction": f"{start_beam}->{beam}",
                "start_beam": start_beam,
                "stop_beam": beam,
                "counted": False
            }

        direction = (start_beam, beam)

        # A full crossing in a direction whose quota is already met is
        # still recorded, but is not counted
        counted = self.full_counts[direction] < self.per_direction

        if counted:
            self.full_counts[direction] += 1

        return {
            "type": FULL,
            "direction": f"{start_beam}->{beam}",
            "start_beam": start_beam,
            "stop_beam": beam,
            "counted": counted
        }

    # --------------------------------------------------

    @property
    def full_1_to_2(self):
        return self.full_counts[(1, 2)]

    @property
    def full_2_to_1(self):
        return self.full_counts[(2, 1)]

    @property
    def full_total(self):
        return self.full_1_to_2 + self.full_2_to_1

    @property
    def target_total(self):
        return 2 * self.per_direction

    @property
    def complete(self):
        return all(
            n >= self.per_direction
            for n in self.full_counts.values()
        )
