# Documentation

This document explains how the code in stock_ledger.py works.
The answers to the task questions are in README.md.


## What the program does

1. It keeps a stock ledger for items which use FIFO valuation.
2. Every transaction is one row in the ledger.
3. When the rate of an old purchase is changed, it recalculates all the rows after it. This is called reposting.
4. It also updates the finished good when the raw material cost changes.


## Ledger row

Every row is a Python dictionary with the below fields.

1. seq. Order in which the row was created. Used when two rows have the same date.
2. item. Item name, for example Milk.
3. date. Posting date.
4. voucher. Voucher number, for example PR-10JAN.
5. qty. Plus for incoming stock and minus for outgoing stock.
6. rate. Incoming rate. Used only for incoming rows.
7. rate_from_voucher. True for a finished good. Its rate is calculated from the raw material consumed in the same voucher.
8. value_change. Value added or removed by this row. Calculated by repost.
9. balance_qty. Stock quantity after this row. Calculated by repost.
10. balance_value. Stock value after this row. Calculated by repost.
11. queue. FIFO layers after this row. Each layer is quantity and rate. Calculated by repost.


## Functions

1. add_entry. Creates one row and adds it to the ledger. It does not calculate anything.
2. fifo_remove. Takes the given quantity from the oldest layers of the queue and returns the cost. Gives an error if stock is not enough.
3. consumed_cost. Returns the total cost of raw material consumed in one voucher.
4. repost. Recalculates all rows on or after a given date. This is the main function.
5. post. Adds a new row and calls repost. If there is an error the ledger is put back as it was.
6. change_rate. Changes the rate of an old purchase and calls repost. If there is an error the ledger is put back as it was.
7. get_row. Finds a row by voucher and item.
8. build_milk_scenario. Creates the transactions given in the task.
9. print_ledger. Prints the ledger as a table.


## How repost works

1. Sort the rows by date and then by creation order.
2. For rows before the changed date, do not change anything. Only remember the queue saved in them.
3. For every row on or after the changed date do the below steps.
4. If it is an incoming row, add a new layer to the queue with its quantity and rate.
5. If the incoming row is a finished good, first calculate its rate. Rate is the cost of raw material consumed in the same voucher divided by the quantity produced.
6. If it is an outgoing row, take the quantity from the oldest layers. The cost taken is the value of that row.
7. Save the balance quantity, balance value and queue in the row.


## Example with the task data

1. change_rate sets the 10 Jan rate to 80 and calls repost from 10 Jan.
2. Opening row is before 10 Jan. Its queue is 100 L at 50. It is not changed.
3. 10 Jan. Add 50 L at 80. Stock value is 9000.
4. 15 Jan. Remove 80 L from the 50 layer. Cost is 4000. Stock value is 5000.
5. 20 Jan. Add 50 L at 60. Stock value is 8000.
6. 21 Jan Milk. Remove 100 L. 20 L at 50, 50 L at 80 and 30 L at 60. Cost is 6800.
7. 21 Jan Milk Powder. Rate is 6800 divided by 10 which is 680.
8. 25 Jan. Remove 10 Kg of Milk Powder. Cost is 6800.


## Error handling

1. If an outgoing row needs more stock than available, fifo_remove gives a ValueError.
2. post and change_rate keep a copy of the ledger before they start. If any error comes, the ledger is restored from the copy. So the ledger is never half updated.
3. change_rate gives an error if the row is not a purchase or if the voucher is not found.


## Tests

1. Tests are in test_stock_ledger.py and they run with pytest.
2. Test_Cases.xlsx lists every test case with steps and expected result.
3. Run pytest -v to see every test by name.
