"""
Small FIFO stock ledger with reposting.

Every ledger row is a plain dict. When an old row is changed we call
repost() which recalculates all rows from that date onwards.
"""

import copy
from datetime import date


def add_entry(ledger, item, posting_date, voucher, qty, rate=0, rate_from_voucher=False):
    """Add one row to the ledger. qty is + for incoming and - for outgoing."""
    row = {
        "seq": len(ledger) + 1,       # order of creation, used when dates are equal
        "item": item,
        "date": posting_date,
        "voucher": voucher,
        "qty": qty,
        "rate": rate,                 # only used for incoming rows
        # True for finished goods: rate is calculated from raw material cost
        "rate_from_voucher": rate_from_voucher,
        # these are filled by repost()
        "value_change": 0,
        "balance_qty": 0,
        "balance_value": 0,
        "queue": [],
    }
    ledger.append(row)
    return row


def fifo_remove(queue, qty):
    """Take qty from the oldest layers. Returns the cost of what was taken."""
    available = sum(layer[0] for layer in queue)
    if qty > available:
        raise ValueError(f"Not enough stock: need {qty}, have {available}")

    cost = 0
    while qty > 0:
        layer = queue[0]
        taken = min(layer[0], qty)
        cost += taken * layer[1]
        layer[0] -= taken
        qty -= taken
        if layer[0] == 0:
            queue.pop(0)
    return cost


def consumed_cost(ledger, voucher):
    """Total cost of the raw materials consumed in a voucher."""
    total = 0
    for row in ledger:
        if row["voucher"] == voucher and row["qty"] < 0:
            total += -row["value_change"]
    return total


def repost(ledger, from_date):
    """
    Recalculate every row dated on or after from_date.

    Rows before from_date are not touched. We only read their stored queue,
    so we do not have to start from the very first transaction.
    """
    ledger.sort(key=lambda row: (row["date"], row["seq"]))
    queues = {}  # item -> current FIFO queue

    for row in ledger:
        if row["date"] < from_date:
            # old row, just remember where this item's queue stands
            queues[row["item"]] = copy.deepcopy(row["queue"])
            continue

        queue = queues.setdefault(row["item"], [])

        if row["qty"] > 0:
            if row["rate_from_voucher"]:
                # finished good: cost of raw material / qty produced
                row["rate"] = consumed_cost(ledger, row["voucher"]) / row["qty"]
            queue.append([row["qty"], row["rate"]])
            row["value_change"] = row["qty"] * row["rate"]
        else:
            row["value_change"] = -fifo_remove(queue, -row["qty"])

        row["balance_qty"] = sum(layer[0] for layer in queue)
        row["balance_value"] = sum(layer[0] * layer[1] for layer in queue)
        row["queue"] = copy.deepcopy(queue)


def post(ledger, item, posting_date, voucher, qty, rate=0, rate_from_voucher=False):
    """Add a row and recalculate. If it fails the ledger is left as it was."""
    backup = copy.deepcopy(ledger)
    try:
        add_entry(ledger, item, posting_date, voucher, qty, rate, rate_from_voucher)
        repost(ledger, posting_date)
    except ValueError:
        ledger[:] = backup
        raise


def change_rate(ledger, voucher, item, new_rate):
    """Change the rate of an old purchase and repost everything after it."""
    backup = copy.deepcopy(ledger)
    try:
        row = get_row(ledger, voucher, item)
        if row["qty"] < 0 or row["rate_from_voucher"]:
            raise ValueError("Only a purchase rate can be changed")
        row["rate"] = new_rate
        repost(ledger, row["date"])
    except ValueError:
        ledger[:] = backup
        raise


def get_row(ledger, voucher, item):
    for row in ledger:
        if row["voucher"] == voucher and row["item"] == item:
            return row
    raise ValueError(f"No row found for {voucher} / {item}")


def build_milk_scenario():
    """The transactions given in the task."""
    ledger = []
    post(ledger, "Milk", date(2026, 1, 1), "OPENING", 100, 50)
    post(ledger, "Milk", date(2026, 1, 10), "PR-10JAN", 50, 60)
    post(ledger, "Milk", date(2026, 1, 15), "DN-15JAN", -80)
    post(ledger, "Milk", date(2026, 1, 20), "PR-20JAN", 50, 60)
    # manufacture: milk goes out, milk powder comes in, same voucher
    post(ledger, "Milk", date(2026, 1, 21), "MFG-21JAN", -100)
    post(ledger, "Milk Powder", date(2026, 1, 21), "MFG-21JAN", 10, rate_from_voucher=True)
    post(ledger, "Milk Powder", date(2026, 1, 25), "DN-25JAN", -10)
    return ledger


def print_ledger(ledger, title):
    print("\n" + title)
    print(f"{'Date':<8}{'Item':<13}{'Voucher':<11}{'Qty':>6}{'Value chg':>11}"
          f"{'Bal qty':>9}{'Bal value':>11}  Queue")
    for row in ledger:
        queue = ", ".join(f"{q:g}@{r:g}" for q, r in row["queue"])
        print(f"{row['date']:%d %b}  {row['item']:<13}{row['voucher']:<11}{row['qty']:>6}"
              f"{row['value_change']:>11g}{row['balance_qty']:>9g}"
              f"{row['balance_value']:>11g}  [{queue}]")


if __name__ == "__main__":
    ledger = build_milk_scenario()
    print_ledger(ledger, "Before: 10 Jan purchase at Rs 60")
    change_rate(ledger, "PR-10JAN", "Milk", 80)
    print_ledger(ledger, "After: 10 Jan purchase at Rs 80")
