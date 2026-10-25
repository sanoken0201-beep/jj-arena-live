"""Capture legal aggression from the runtime before an action is applied."""
def can_increase_wager(legal: dict, current_bet: int) -> int | None:
    if legal.get("can_act") is not True:
        return None
    if legal.get("can_raise") is True:
        return 1
    # A short all-in raise is a real aggressive option, despite can_raise=False.
    if legal.get("can_all_in") is True and legal.get("max_raise_to", 0) > current_bet:
        return 1
    return 0
