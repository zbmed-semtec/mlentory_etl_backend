# Platform catalog log

Add the newest update at the top. Leave every earlier update below it.

### 2026-11-10 - catalog snapshot

| Platform     | Hosted             | Read by the ETL                                                       | Stored   | Shown in the UI   | Hidden mainly because                                 |                                                                            |
| ------------ | -----------------: | --------------------------------------------------------------------: | -------: | ----------------: | ----------------------------------------------------: | -------------------------------------------------------------------------- |
| Hugging Face | 3,227,261          | 717,742 in the pinned librarian snapshot, then 237,591 kept by config | 584,153  | 330,536           | 229,161 missing `license`, 155,270 missing `ml_tasks` |                                                                            |
| Kaggle       | 44,941 model pages | 44,829 parent cards downloaded, 112 failed                            | Finished | 51,265 variations | 7,497                                                 | 43,740 missing `ml_tasks`, 41,892 missing `keywords`, 33 `license` Unknown |
| AI4Life      | 173 models         | 148 at the 27 July 2026 extract                                       | 149      | 130               | 18 missing `ml_tasks`, 1 missing `readme`             |                                                                            |

| Platform     | Run                            |            | Indexed this run | Notes                                |
| ------------ | ------------------------------ | ---------- | ---------------: | ------------------------------------ |
| Kaggle       | `2026-10-20_07-48-58_6b826216` | 2026-10-23 | 19,221           | Neo4j 19,221, index errors 0         |
| Kaggle       | `2026-10-17_09-42-15_d787cc56` | 2026-10-19 | 10,243           | Neo4j 10,243, index errors 0         |
| Kaggle       | `2026-10-13_13-24-38_d703e04f` | 2026-10-15 | 11,940           | Neo4j 11,940, index errors 0         |
| Kaggle       | `2026-10-09_13-26-14_e232f127` | 2026-10-10 | 9,861            | Neo4j 9,861, index errors 0          |
| Kaggle       | `2026-10-08_10-37-25_e753c06f` | 2026-10-09 | 4,842            | Neo4j 4,842, index errors 0          |
| AI4Life      | `2026-07-27_06-08-47_4bfd556b` | 2026-07-27 | 148              | Neo4j 148, index errors 0            |
| AI4Life      | `2026-07-15_14-52-43_8786599f` | 2026-07-15 | 139              | Neo4j 139, index errors 0            |
| Hugging Face | —                              | —          | —                | No Elasticsearch load report on disk |
