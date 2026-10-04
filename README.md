# FIFO Stock Reposting

This is a simple Python program that I created to understand the Stock Reposting and Valuation problem and to demonstrate my approach to solving it using FIFO logic.
It is a small standalone program and does not need Frappe or ERPNext to run.


## How to run

1. Python 3.8 or above is needed.
2. To see the result run the below command. It prints the ledger before and after the change.

   python stock_ledger.py

3. To run the test cases install pytest and run it.

   pip install pytest
   pytest

4. The result should be 11 passed.
5. To see the name of every test case run the below command. Every line should show PASSED.

   pytest -v

6. The file Test_Cases.xlsx has the test scenario, all the test cases and the expected results. The test function names in that file are same as the names shown by pytest, so it is easy to check that all test cases are covered.


## The scenario

1. Items are Milk and Milk Powder. Both use FIFO. One warehouse is used.
2. Opening stock of Milk is 100 L at Rs 50.
3. 10 Jan Purchase Receipt of Milk 50 L at Rs 60.
4. 15 Jan Delivery Note of Milk 80 L.
5. 20 Jan Purchase Receipt of Milk 50 L at Rs 60.
6. 21 Jan Manufacture entry. 100 L Milk is consumed and 10 Kg Milk Powder is produced.
7. 25 Jan Delivery Note of Milk Powder 10 Kg.
8. Then the rate of the 10 Jan Purchase Receipt is changed from Rs 60 to Rs 80.


## Result before and after the change

1. 10 Jan purchase. Value was 3000 and becomes 4000. Stock value was 8000 and becomes 9000.
2. 15 Jan delivery. Cost is 4000 before and after. Stock value was 4000 and becomes 5000.
3. 20 Jan purchase. Value is 3000 before and after. Stock value was 7000 and becomes 8000.
4. 21 Jan Milk consumed. Cost was 5800 and becomes 6800. Stock value stays 1200.
5. 21 Jan Milk Powder produced. Rate was 580 per Kg and becomes 680 per Kg.
6. 25 Jan Milk Powder delivery. Cost was 5800 and becomes 6800.
7. Working for 21 Jan after the change. 20 L at 50 plus 50 L at 80 plus 30 L at 60 gives 6800.
8. The extra cost is 1000, that is 50 L multiplied by Rs 20. All of it goes to the cost of Milk Powder sold.
9. Final Milk stock is 20 L at Rs 60 which is 1200. It does not change.


## Question 1. What transactions in Stock should be affected

1. All stock ledger entries on or after 10 Jan have to be reposted, for both Milk and Milk Powder. Some of them get a new cost and some of them get only a new balance.
2. Opening stock is not affected because it is before the change.
3. The 10 Jan purchase is affected because its own rate is changed.
4. The 21 Jan Milk consumption is affected because it uses the 50 L bought on 10 Jan.
5. The 21 Jan Milk Powder entry is affected because its rate comes from the cost of Milk consumed.
6. The 25 Jan Milk Powder delivery is affected because the Milk Powder rate is changed.
7. The 15 Jan delivery cost is not changed, because FIFO takes that 80 L from the opening stock at Rs 50.
8. But the 15 Jan and 20 Jan entries still have to be updated, because the stock value and FIFO queue saved in them are now different.
9. Bin value also changes. With perpetual inventory the accounting entries of the 10 Jan purchase and the 25 Jan delivery change. The 21 Jan manufacture entry will have no accounting entry when Milk and Milk Powder use the same stock account, because the amount going out and coming in cancel each other.
10. This answer assumes Milk is not a batch item. If Milk has batches with batch wise valuation, the cost is taken from the batch which is picked and not from the FIFO queue. Then only the transactions which use the 10 Jan batch are affected. If the 10 Jan and 20 Jan receipts share one batch, the batch rate becomes 70 and the final Milk stock value also changes.
11. The answer also depends on the valuation method. With Moving Average the 15 Jan delivery cost also changes, from 4266.67 to 4800.


## Question 2. How should ERPNext recalculate the later transactions

1. Take the balance and FIFO queue saved in the entry just before the changed entry.
2. Go through all later entries in order of posting date and time. If time is same use the creation order.
3. For an incoming entry add a new layer with its quantity and rate.
4. For an outgoing entry take the quantity from the oldest layers. The total of what is taken is the cost.
5. Save the new value, balance quantity, balance value and queue in each entry.
6. If the outgoing entry is part of a manufacture entry, calculate the finished good rate again and repost that item also.
7. At the end update the Bin and make the accounting entries again for the vouchers whose value changed.
8. The order is important because the result of one entry is the starting point of the next entry.


## Question 3. How I designed the reposting logic for FIFO

1. The logic is in the function repost in stock_ledger.py.
2. Every row saves the FIFO queue after it. So repost does not start from the first transaction.
3. Rows before the changed date are only read to get the queue. They are not changed.
4. Rows on or after the changed date are processed in date order.
5. A purchase adds a layer. A delivery or consumption takes from the oldest layer first.
6. A finished good row is marked as rate from voucher. Its rate is the cost of raw material consumed in the same voucher divided by the quantity produced.
7. All items are processed together in date order. So when the Milk Powder row is reached the new Milk cost is already calculated. This is how the change goes from Milk to Milk Powder.
8. If something fails, for example stock becomes negative, the ledger is put back as it was.
9. Running repost two times gives the same result.
10. To keep the code small all items are replayed from the changed date. A real system should replay only the changed item and the items which depend on it, stop when a row comes out same as before, run in a background job, and lock the item while it runs.


## Question 4. Problems if a running balance is stored in every Stock Ledger Entry

1. One change in an old entry needs all later entries of that item to be written again.
2. It becomes slow when an item has many entries over the years.
3. New transactions posted while reposting is running can read wrong balances.
4. Until reposting is finished the stock reports and accounts show a mix of old and new values.
5. If reposting stops in the middle, half of the entries are updated and half are not.
6. The change spreads to other items and warehouses through manufacture and transfer, so the work is hard to predict.
7. Old reports and closed periods show different numbers after reposting.
8. Small rounding differences can add up over many rows.
9. Saving the queue in every row takes more storage.
10. The good side is that balance on any date can be read from one row, and the saved queue gives a starting point for reposting.


## Files

1. stock_ledger.py has the ledger rows, FIFO logic, repost function and the task scenario.
2. test_stock_ledger.py has the test cases.
3. Test_Cases.xlsx has the test scenario, test cases and expected results.


## Design decisions

1. I wrote a separate small program and did not change ERPNext core because my aim was to show the logic in a simple way.
2. Rows are plain dictionaries and the logic is a few functions, so it is easy to read.
3. Negative stock is not allowed. It gives an error and nothing is saved.
4. Only FIFO is covered, with one warehouse and one finished good per manufacture entry.
5. Accounting entries are not created.


## Test cases

1. Values before the change and after the change as per the task.
2. Opening stock is not touched.
3. Final Milk stock is same after the change.
4. Rate decrease.
5. Repost two times gives same result.
6. Changing the last purchase does not change earlier rows.
7. Backdated purchase changes the later cost.
8. Balance value is always equal to the total of the queue layers.
9. Delivering more than the stock gives an error and nothing is saved.
10. Changing the rate of a delivery or a finished good gives an error.
