# Transaction reconstruction and conversion summary

Command: `.venv/bin/python -m feature_workspace.prepare_transactions`

Source and destination amounts use first/last executed legs. VALUE is already normalized; XRP SOURCE_VALUE is drops. Assets retain issuer identity. USD amounts use separate endpoint asset prices at the transaction's containing UTC hour. Fees remain separate.

Conversion steps count adjacent asset changes, including issuer changes; they do not count same-asset legs. IS_CONVERSION is steps > 0, even for a path returning to its original asset. Intermediaries are unique path addresses excluding sender/receiver, not AML layering evidence.

| Split | Transactions | With conversion | Actual steps | Without conversion | Conversion % |
|---|---:|---:|---:|---:|---:|
| train | 40,131 | 16,450 | 20,426 | 23,681 | 40.9908% |
| validation | 33,862 | 17,798 | 22,035 | 16,064 | 52.5604% |
| test | 40,101 | 20,261 | 25,171 | 19,840 | 50.5249% |

| Split | 0 steps | 1 step | 2 steps |
|---|---:|---:|---:|
| train | 23,681 | 12,474 | 3,976 |
| validation | 16,064 | 13,561 | 4,237 |
| test | 19,840 | 15,351 | 4,910 |

## train: ten most common endpoint asset pairs

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `XRP` | `XRP` | 9,668 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | 4,611 |
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | 3,233 |
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:USD` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:USD` | 3,178 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | 2,991 |
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | 895 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `XRP` | 890 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | 879 |
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:USD` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | 879 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | 876 |

Ten most common pairs among conversion transactions only:

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | 895 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `XRP` | 890 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | 879 |
| `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:USD` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | 879 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | 876 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | 863 |
| `XRP` | `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:USD` | 855 |
| `XRP` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:USD` | 831 |
| `XRP` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | 829 |
| `r99vy4o5fXhC3PwEXEpnc1f9Mss4aCzYBW:GBP` | `rLeMq5iFyEhgHLfBxeu4eRQWEGGdeL8hXK:EUR` | 829 |

Sample checks (full hashes, paths, prices and all fields are in the JSON report):

| Sample | Source units × USD price | Source USD | Destination units × USD price | Destination USD | Steps |
|---|---|---:|---|---:|---:|
| direct_xrp | 1167.184470 × 0.653280 | 762.49827056 | 1167.184470 × 0.653280 | 762.49827056 | 0 |
| direct_iou | 1.715004 × 1.099637 | 1.88588185 | 1.715004 × 1.099637 | 1.88588185 | 0 |
| one_conversion_step | 104.674336 × 1.016492 | 106.40062515 | 163.125642 × 0.652001 | 106.35808171 | 1 |
| two_conversion_steps | 9.496353 × 1.316071 | 12.49787479 | 12.323166 × 1.008323 | 12.42573171 | 2 |

## validation: ten most common endpoint asset pairs

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `XRP` | `XRP` | 8,609 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 2,607 |
| `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | 1,692 |
| `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:GBP` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:GBP` | 1,592 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | 1,564 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | 954 |
| `XRP` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:GBP` | 950 |
| `XRP` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 941 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 940 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | 932 |

Ten most common pairs among conversion transactions only:

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | 954 |
| `XRP` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:GBP` | 950 |
| `XRP` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 941 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 940 |
| `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | 932 |
| `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:GBP` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | 915 |
| `XRP` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:EUR` | 909 |
| `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | `rwKVMHDA73raYeKwGjfMiWSjzeF59HwPxG:USD` | 904 |
| `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | `XRP` | 901 |
| `XRP` | `rUz26aCT6t4jAf5Guo78dv3bXRjFNWSgQs:USD` | 897 |

Sample checks (full hashes, paths, prices and all fields are in the JSON report):

| Sample | Source units × USD price | Source USD | Destination units × USD price | Destination USD | Steps |
|---|---|---:|---|---:|---:|
| direct_xrp | 51.533626 × 0.652696 | 33.63579156 | 51.533626 × 0.652696 | 33.63579156 | 0 |
| direct_iou | 54.847869 × 1.008183 | 55.29668911 | 54.847869 × 1.008183 | 55.29668911 | 0 |
| one_conversion_step | 20.924894 × 1.301716 | 27.23826932 | 27.043222 × 1.002002 | 27.09736253 | 1 |
| two_conversion_steps | 184.058507 × 0.999473 | 183.96150817 | 140.134063 × 1.306478 | 183.08207036 | 2 |

## test: ten most common endpoint asset pairs

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `XRP` | `XRP` | 10,557 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | 2,908 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 2,248 |
| `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | 2,067 |
| `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:USD` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:USD` | 2,060 |
| `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 1,133 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `XRP` | 1,088 |
| `XRP` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 1,072 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | 1,068 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | `XRP` | 1,047 |

Ten most common pairs among conversion transactions only:

| Source asset | Destination asset | Transactions |
|---|---|---:|
| `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 1,133 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `XRP` | 1,088 |
| `XRP` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 1,072 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | 1,068 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | `XRP` | 1,047 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:USD` | 1,041 |
| `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:USD` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | 1,040 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | 1,029 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | `rDafjsQScwoVYNW1Sg91oe1ALkvqvK2LTW:GBP` | 1,018 |
| `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:EUR` | `rNnBxvYbzhfnR6d8dLDRHRVVHgagj6aLVh:USD` | 1,013 |

Sample checks (full hashes, paths, prices and all fields are in the JSON report):

| Sample | Source units × USD price | Source USD | Destination units × USD price | Destination USD | Steps |
|---|---|---:|---|---:|---:|
| direct_xrp | 13.980514 × 0.642312 | 8.97985191 | 13.980514 × 0.642312 | 8.97985191 | 0 |
| direct_iou | 136.729824 × 1.106783 | 151.33024480 | 136.729824 × 1.106783 | 151.33024480 | 0 |
| one_conversion_step | 14.186099 × 1.293186 | 18.34526462 | 28.589410 × 0.638107 | 18.24310265 | 1 |
| two_conversion_steps | 1.686160 × 1.099020 | 1.85312356 | 1.868822 × 0.988730 | 1.84776038 | 2 |

All transaction joins, contiguous leg indices, path endpoints, delivered JSON, units, fees, hourly endpoint rates, source-file hashes and Parquet round-trips passed. Destination USD matches the supplied payment helper for every transaction in every split. Sorted raw legs retain every original column/value/type. Labels and annotation metadata were not read.

The current data happens to change assets at every adjacent leg, so steps = legs − 1 here. Tests also cover same-asset extra legs and return-to-source-asset paths to avoid making that assumption.

Generated tables are under feature_workspace/generated/transaction_tables_v1/{train,validation,test}/. Original datasets and the measured baseline are preserved. No model was trained in this step.
