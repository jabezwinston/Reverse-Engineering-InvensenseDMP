# DMP Rosetta stones: driver-assembled instruction sequences

Every place a vendor driver hand-assembles a few DMP instruction bytes and writes them into a *named* config point of the firmware image, with the function name that tells us what the sequence does. Machine-readable copy: `rosetta.json` (same directory).

## Sources and lineages

| image | source | key resolution | DINA lineage | verification image |
|---|---|---|---|---|
| 3062 | `emd612__inv_mpu_dmp_motion_driver.c` (eMD 6.12, MPU-6050/9150) | `#define`s at top of the driver + `emd612__dmpmap.h` | `emd612` (DINAF8=0xf0, DINAC0..C5=b0 b1 b4 b5 b8 b9, DINBC0..C6=c0 c2 c4 c6, DINBF8=0xf8) | eMD embedded `dmp_memory[]` (pristine). The corpus file `ae42d0be801847e5_3062.bin` is the i2cdev MotionApps612 copy, a **live dump** (282 bytes differ, all in data banks 0-3 plus the CFG_8/CFG_15/CFG_27/CFG_6 config points); reported separately as "dump". |
| 1024 | `ics-mr0__mlsdk__mllite__{ml,mlFIFO,mlBiasNoMotion,mlsupervisor}.c` | `KEY_*` -> `dmpDefault.c` dmpTConfig | `mlsdk_mpu3050` (DINAF8=0xf8, DINAC0..C5=c0..c5, no DINB*) - this is the `CONFIG_MPU_SENSORS_MPU3050` build; the 1024 image bytes (e.g. `f9`/`fa` prefixes at CFG_12/CFG_8, `c0` at CFG_15 region) confirm the 0xf8 encoding | `4952db90a63f577a_1024.bin` (identical to `dmpDefault.c` array) |
| 1923 | same mlsdk files | `KEY_*` -> `dmpDefaultMantis.c` dmpTConfig | `mlsdk_mpu6050` (identical values to `emd612`) - `CONFIG_MPU_SENSORS_MPU6050B1` build | `2e40b3ba8a7227f9_1923.bin` (identical to `dmpDefaultMantis.c` array) |
| 2639 | `hammerhead-kk__inv_mpu_misc.c` | `KEY_*` -> `hammerhead-kk__dmpDefaultMPU6050.c` + `hammerhead-kk__dmpmap.h` | `hammerhead` (identical values to `emd612`) | `f80d502b66daab2f_2639.bin` |
| 1929 | `i2cdev_MPU6050_6Axis_MotionApps20.cpp` | bank*256+offset | n/a (literal bytes) | `d79e55736bb5ea91_1929.bin` (identical to embedded array) |
| 1962 | `i2cdev_MPU6050_9Axis_MotionApps41.cpp` | bank*256+offset (i2cdev comments name the mlsdk keys) | n/a (literal bytes) | `fab8d4c6fcf535c6_1962.bin` (identical to embedded array) |
| 3062 | `i2cdev_MPU6050_6Axis_MotionApps612.cpp` | - | - | no config writes at all (only the firmware block + register setup); its `dmpMemory[]` is the dump described above |

Column key: **img default** = do the bytes currently in the verification image at that address equal this variant (`yes`/`no`/`-` unresolved). For 3062 the extra **dump** column is the i2cdev live copy. For data writes the image bytes are shown instead.

Conventions used in the sequences (observed, not asserted beyond what the functions say): `a3` (= DINAA0+3) is the universal "skip / do nothing" filler in output slots; `f1`/`f9` (= DINAF8+1 per lineage) is a common prefix/filler; `d8`/`d9`/`da` appear as 1-byte enable/disable toggles; `ff` disables/halts (pedometer) and terminates every image.

## FIFO output selection

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_15 | 2727 | accel+gyro | `a3 c0 c8 c2 c4 cc c6 a3 a3 a3` |  | mask has SEND_RAW_ACCEL and SEND_ANY_GYRO | no | yes | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_15 | 2727 | accel_only | `a3 c0 c8 c2 a3 a3 a3 a3 a3 a3` |  | mask has SEND_RAW_ACCEL only | no | no | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_15 | 2727 | gyro_only | `a3 a3 a3 a3 c4 cc c6 a3 a3 a3` |  | mask has SEND_ANY_GYRO only | no | no | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_15 | 2727 | none | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |  | neither raw accel nor gyro | yes | no | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_GYRO_RAW_DATA | 2722 | cal_gyro | `b2 8b b6 9b` |  | DMP_FEATURE_SEND_CAL_GYRO | yes | yes | `b2 8b b6 9b` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_GYRO_RAW_DATA | 2722 | raw_gyro | `b0 80 b4 90` | `DINAC0 DINA80 DINAC2 DINA90` | DMP_FEATURE_SEND_RAW_GYRO | no | no | `b2 8b b6 9b` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_27 | 2742 | gesture_on | `20` | `DINA20` | mask has TAP or ANDROID_ORIENT | no | no | `a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_27 | 2742 | gesture_off | `d8` |  | otherwise | no | yes | `a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_6x_lp_quat` | CFG_8 | 2718 | enable | `20 28 30 38` | `DINA20 DINA28 DINA30 DINA38` | enable=1 | no | yes | `a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_6x_lp_quat` | CFG_8 | 2718 | disable | `a3 a3 a3 a3` |  | enable=0 | yes | no | `a3 a3 a3 a3` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_lp_quat` | CFG_LP_QUAT | 2712 | enable | `c0 c2 c4 c6` | `DINBC0 DINBC2 DINBC4 DINBC6` | enable=1 | no | no | `8b 8b 8b 8b` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_lp_quat` | CFG_LP_QUAT | 2712 | disable | `8b 8b 8b 8b` |  | enable=0 | yes | yes | `8b 8b 8b 8b` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 797 | all_32bit | `f9 28 30 38` | `DINAF8+1 DINA28 DINA30 DINA38` | elements=all, accuracy=INV_32_BIT | no |  | `f9 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 797 | all_16bit | `fa 28 30 38` | `DINAF8+2 DINA28 DINA30 DINA38` | elements=all, accuracy=INV_16_BIT | no |  | `f9 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 797 | off | `f9 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy=0 / no elements (each unused element -> DINAA0+3) | yes |  | `f9 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 1894 | all_32bit | `f1 28 30 38` | `DINAF8+1 DINA28 DINA30 DINA38` | elements=all, accuracy=INV_32_BIT | no |  | `f1 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 1894 | all_16bit | `f2 28 30 38` | `DINAF8+2 DINA28 DINA30 DINA38` | elements=all, accuracy=INV_16_BIT | no |  | `f1 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_accel (via inv_construct3_fifo)` | KEY_CFG_12 (CFG_12) | 1894 | off | `f1 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy=0 / no elements (each unused element -> DINAA0+3) | yes |  | `f1 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro` | KEY_CFG_GYRO_SOURCE (CFG_GYRO_SOURCE) | 777 | from_quaternion | `95` | `DINA90+5` | fifo_obj.gyro_source == INV_GYRO_FROM_QUATERNION | yes |  | `95` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro` | KEY_CFG_GYRO_SOURCE (CFG_GYRO_SOURCE) | 777 | raw | `9a` | `DINA90+10` | otherwise | no |  | `95` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro` | KEY_CFG_GYRO_SOURCE (CFG_GYRO_SOURCE) | 1859 | from_quaternion | `95` | `DINA90+5` | fifo_obj.gyro_source == INV_GYRO_FROM_QUATERNION | yes |  | `95` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro` | KEY_CFG_GYRO_SOURCE (CFG_GYRO_SOURCE) | 1859 | raw | `9a` | `DINA90+10` | otherwise | no |  | `95` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 778 | quat_source_32bit | `f9 20 28 30` | `DINAF8+1 DINA20 DINA28 DINA30` | gyro from quaternion, all, 32-bit | no |  | `f9 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 778 | raw_32bit | `f9 28 30 38` | `DINAF8+1 DINA28 DINA30 DINA38` | raw gyro, all, 32-bit | no |  | `f9 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 778 | raw_16bit | `fa 28 30 38` | `DINAF8+2 DINA28 DINA30 DINA38` | raw gyro, all, 16-bit | no |  | `f9 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 778 | off | `f9 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3` | no elements | yes |  | `f9 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 1860 | quat_source_32bit | `f1 20 28 30` | `DINAF8+1 DINA20 DINA28 DINA30` | gyro from quaternion, all, 32-bit | no |  | `f1 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 1860 | raw_32bit | `f1 28 30 38` | `DINAF8+1 DINA28 DINA30 DINA38` | raw gyro, all, 32-bit | no |  | `f1 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 1860 | raw_16bit | `f2 28 30 38` | `DINAF8+2 DINA28 DINA30 DINA38` | raw gyro, all, 16-bit | no |  | `f1 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_gyro (via inv_construct3_fifo)` | KEY_CFG_9 (CFG_9) | 1860 | off | `f1 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3` | no elements | yes |  | `f1 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 772 | all_32bit | `f9 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | INV_32_BIT | no |  | `f9 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 772 | all_16bit | `fa 20 28 30 38` | `DINAF8+2 DINA20 DINA28 DINA30 DINA38` | INV_16_BIT | no |  | `f9 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 772 | off | `f9 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy 0 | yes |  | `f9 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 1854 | all_32bit | `f1 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | INV_32_BIT | no |  | `f1 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 1854 | all_16bit | `f2 20 28 30 38` | `DINAF8+2 DINA20 DINA28 DINA30 DINA38` | INV_16_BIT | no |  | `f1 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quaternion` | KEY_CFG_8 (CFG_8) | 1854 | off | `f1 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy 0 | yes |  | `f1 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 783 | all_32bit | `f9 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | INV_32_BIT | no |  | `f9 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 783 | all_16bit | `fa 20 28 30 38` | `DINAF8+2 DINA20 DINA28 DINA30 DINA38` | INV_16_BIT | no |  | `f9 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 783 | off | `f9 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy 0 | yes |  | `f9 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 1865 | all_32bit | `f1 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | INV_32_BIT | no |  | `f1 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 1865 | all_16bit | `f2 20 28 30 38` | `DINAF8+2 DINA20 DINA28 DINA30 DINA38` | INV_16_BIT | no |  | `f1 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_cntrl_data` | KEY_CFG_1 (CFG_1) | 1865 | off | `f1 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | accuracy 0 | yes |  | `f1 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_packet_number` | KEY_CFG_23 (CFG_23) | 814 | on | `28` | `DINA28` | element ref > 0 | no |  | `a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_packet_number` | KEY_CFG_23 (CFG_23) | 814 | off | `fb` | `DINAF8+3` | ref == 0 | no |  | `a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_packet_number` | KEY_CFG_23 (CFG_23) | 1911 | on | `28` | `DINA28` | element ref > 0 | no |  | `a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_packet_number` | KEY_CFG_23 (CFG_23) | 1911 | off | `f3` | `DINAF8+3` | ref == 0 | no |  | `a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_set_footer` | KEY_CFG_16 (CFG_16) | 815 | add_footer | `30` | `DINA30` | packet non-empty and no footer | no |  | `a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_set_footer` | KEY_CFG_16 (CFG_16) | 815 | remove_footer | `a3` | `DINAA0+3` | packet would be footer-only | yes |  | `a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_set_footer` | KEY_CFG_16 (CFG_16) | 1912 | add_footer | `30` | `DINA30` | packet non-empty and no footer | no |  | `a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_set_footer` | KEY_CFG_16 (CFG_16) | 1912 | remove_footer | `a3` | `DINAA0+3` | packet would be footer-only | yes |  | `a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_sensor_data (MPU6050 body)` | KEY_CFG_15 (CFG_15) | 1876 | all_on | `ca c4 cc c6 c0 c8 c2` | `DINACA DINBC4 DINACC DINBC6 DINBC0 DINAC8 DINBC2` | elements=all | no |  | `a3 a3 a3 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_sensor_data (MPU6050 body)` | KEY_CFG_15 (CFG_15) | 1876 | all_off | `a3 a3 a3 a3 a3 a3 a3` | `DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | elements=0 | yes |  | `a3 a3 a3 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_sensor_data (MPU3050 body)` | KEY_CFG_15 (CFG_15) | 790 | all_on | `20 28 30 38` | `DINA20 DINA28 DINA30 DINA38` | elements=all | no |  | `a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_sensor_data (MPU3050 body)` | KEY_CFG_15 (CFG_15) | 790 | all_off | `a3 a3 a3 a3` | `DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | elements=0 | yes |  | `a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_external_sensor_data` | KEY_CFG_EXTERNAL (CFG_EXTERNAL) | 1884 | all_on | `c2 ca c4 c0 c8 cc` | `DINBC2 DINACA DINBC4 DINBC0 DINAC8 DINACC` | elements=all | no |  | `a3 a3 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_external_sensor_data` | KEY_CFG_EXTERNAL (CFG_EXTERNAL) | 1884 | all_off | `a3 a3 a3 a3 a3 a3` | `DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | elements=0 | yes |  | `a3 a3 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP0 (CFG_TAP0) | 802 | all_on | `f9 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | elements 0-3 | no |  | `f9 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP0 (CFG_TAP0) | 802 | all_off | `f9 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | none | yes |  | `f9 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP0 (CFG_TAP0) | 1899 | all_on | `f1 20 28 30 38` | `DINAF8+1 DINA20 DINA28 DINA30 DINA38` | elements 0-3 | no |  | `f1 a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP0 (CFG_TAP0) | 1899 | all_off | `f1 a3 a3 a3 a3` | `DINAF8+1 DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | none | yes |  | `f1 a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP4 (CFG_TAP4) | 808 | all_on | `20 28 30 38` | `DINA20 DINA28 DINA30 DINA38` | elements 4-7 | no |  | `a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP4 (CFG_TAP4) | 808 | all_off | `a3 a3 a3 a3` | `DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | none | yes |  | `a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP4 (CFG_TAP4) | 1905 | all_on | `20 28 30 38` | `DINA20 DINA28 DINA30 DINA38` | elements 4-7 | no |  | `a3 a3 a3 a3` |
| 1923 | mlsdk/mlFIFO.c | `inv_send_quantized_accel` | KEY_CFG_TAP4 (CFG_TAP4) | 1905 | all_off | `a3 a3 a3 a3` | `DINAA0+3 DINAA0+3 DINAA0+3 DINAA0+3` | none | yes |  | `a3 a3 a3 a3` |
| 1024 | mlsdk/mlFIFO.c | `inv_send_eis` | KEY_P_EIS_FIFO_XSHIFT | - | all_on | `28 30 38` | `DINA28 DINA30 DINA38` | elements=all | - |  | - |
| 1024 | mlsdk/mlFIFO.c | `inv_send_eis` | KEY_P_EIS_FIFO_XSHIFT | - | all_off | `a7 a7 a7` | `DINAA0+7 DINAA0+7 DINAA0+7` | none | - |  | - |
| 1923 | mlsdk/mlFIFO.c | `inv_send_eis` | KEY_P_EIS_FIFO_XSHIFT | - | all_on | `28 30 38` | `DINA28 DINA30 DINA38` | elements=all | - |  | - |
| 1923 | mlsdk/mlFIFO.c | `inv_send_eis` | KEY_P_EIS_FIFO_XSHIFT | - | all_off | `a7 a7 a7` | `DINAA0+7 DINAA0+7 DINAA0+7` | none | - |  | - |

- **dmp_enable_feature / CFG_15** (img 3062): "Send sensor data to the FIFO." 10-byte slot; a3 = no-op/skip; c0 c8 c2 = raw accel X/Y/Z out, c4 cc c6 = gyro X/Y/Z out. Byte 0 and bytes 7-9 are always a3.
- **dmp_enable_feature / CFG_GYRO_RAW_DATA** (img 3062): Selects calibrated vs raw gyro for FIFO output (only written when SEND_ANY_GYRO). Cal: b2 8b b6 9b; raw: DINAC0 DINA80 DINAC2 DINA90.
- **dmp_enable_feature / CFG_27** (img 3062): "Send gesture data to the FIFO." DINA20 = write 4-byte gesture word to FIFO; 0xd8 = do not.
- **dmp_enable_6x_lp_quat / CFG_8** (img 3062): "Generate 6-axis quaternions from the DMP" - 4 bytes 20 28 30 38 push quat W/X/Y/Z to FIFO; a3 x4 disables.
- **dmp_enable_lp_quat / CFG_LP_QUAT** (img 3062): "Generate 3-axis quaternions from the DMP" - DINBC0 DINBC2 DINBC4 DINBC6 (c0 c2 c4 c6) enable; 8b x4 disable.
- **inv_send_accel (via inv_construct3_fifo) / KEY_CFG_12** (img 1024): Sends accelerometer X/Y/Z to FIFO. Prefix F8+1 (32-bit) or F8+2 (16-bit); 28/30/38 = element select; A0+3 = skip.
- **inv_send_accel (via inv_construct3_fifo) / KEY_CFG_12** (img 1923): Sends accelerometer X/Y/Z to FIFO. Prefix F8+1 (32-bit) or F8+2 (16-bit); 28/30/38 = element select; A0+3 = skip.
- **inv_send_gyro / KEY_CFG_GYRO_SOURCE** (img 1024): Selects gyro data source for FIFO: DINA90+5 (0x95) = gyro derived from quaternion; DINA90+10 (0x9a) = raw gyro.
- **inv_send_gyro / KEY_CFG_GYRO_SOURCE** (img 1923): Selects gyro data source for FIFO: DINA90+5 (0x95) = gyro derived from quaternion; DINA90+10 (0x9a) = raw gyro.
- **inv_send_gyro (via inv_construct3_fifo) / KEY_CFG_9** (img 1024): Gyro X/Y/Z to FIFO. Element bytes are 20/28/30 when sourced from quaternion, 28/30/38 when raw; 16-bit -> prefix F8+2.
- **inv_send_gyro (via inv_construct3_fifo) / KEY_CFG_9** (img 1923): Gyro X/Y/Z to FIFO. Element bytes are 20/28/30 when sourced from quaternion, 28/30/38 when raw; 16-bit -> prefix F8+2.
- **inv_send_quaternion / KEY_CFG_8** (img 1024): Quaternion W/X/Y/Z (4 elements) to FIFO: {F8+1, 20, 28, 30, 38}; 16-bit -> F8+2; unused -> A0+3.
- **inv_send_quaternion / KEY_CFG_8** (img 1923): Quaternion W/X/Y/Z (4 elements) to FIFO: {F8+1, 20, 28, 30, 38}; 16-bit -> F8+2; unused -> A0+3.
- **inv_send_cntrl_data / KEY_CFG_1** (img 1024): Control data (4 elements) to FIFO; same encoding as quaternion.
- **inv_send_cntrl_data / KEY_CFG_1** (img 1923): Control data (4 elements) to FIFO; same encoding as quaternion.
- **inv_send_packet_number / KEY_CFG_23** (img 1024): Rolling packet counter: DINA28 enables, DINAF8+3 disables.
- **inv_send_packet_number / KEY_CFG_23** (img 1923): Rolling packet counter: DINA28 enables, DINAF8+3 disables.
- **inv_set_footer / KEY_CFG_16** (img 1024): FIFO footer: DINA30 adds 2-byte footer; DINAA0+3 removes it.
- **inv_set_footer / KEY_CFG_16** (img 1923): FIFO footer: DINA30 adds 2-byte footer; DINAA0+3 removes it.
- **inv_send_sensor_data (MPU6050 body) / KEY_CFG_15** (img 1923): Raw sensor data to FIFO (7 elements): el1 temp=DINACA, el2=DINBC4, el3=DINACC, el4=DINBC6, el5=DINBC0, el6=DINAC8, el7=DINBC2; unused -> A0+3. (Temp/gyro XYZ/accel XYZ order per raw register layout.)
- **inv_send_sensor_data (MPU3050 body) / KEY_CFG_15** (img 1024): Raw data to FIFO on 3050 (4 groups): bits 0x03->DINA20, 0x0C->DINA28, 0x30->DINA30, 0x40->DINA38; unused -> A0+3.
- **inv_send_external_sensor_data / KEY_CFG_EXTERNAL** (img 1923): External (compass/aux) raw data to FIFO (6 elements): el1=DINBC2, el2=DINACA, el3=DINBC4, el4=DINBC0, el5=DINAC8, el6=DINACC; unused -> A0+3.
- **inv_send_quantized_accel / KEY_CFG_TAP0** (img 1024): Quantized accel samples 0-3 to FIFO: {F8+1, 20, 28, 30, 38}; unused -> A0+3.
- **inv_send_quantized_accel / KEY_CFG_TAP0** (img 1923): Quantized accel samples 0-3 to FIFO: {F8+1, 20, 28, 30, 38}; unused -> A0+3.
- **inv_send_quantized_accel / KEY_CFG_TAP4** (img 1024): Quantized accel samples 4-7 to FIFO: {20, 28, 30, 38}; unused -> A0+3.
- **inv_send_quantized_accel / KEY_CFG_TAP4** (img 1923): Quantized accel samples 4-7 to FIFO: {20, 28, 30, 38}; unused -> A0+3.
- **inv_send_eis / KEY_P_EIS_FIFO_XSHIFT** (img 1024): EIS data to FIFO: {28, 30, 38}; unused -> DINAA0+7 (0xa7). Key not present in either dmpTConfig table.
- **inv_send_eis / KEY_P_EIS_FIFO_XSHIFT** (img 1923): EIS data to FIFO: {28, 30, 38}; unused -> DINAA0+7 (0xa7). Key not present in either dmpTConfig table.

## FIFO rate

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_fifo_rate` | CFG_6 | 2753 | regs_end | `fe f2 ab c4 aa f1 df df bb af df df` | `DINAFE DINAF2 DINAAB 0xc4 DINAAA DINAF1 DINADF DINADF 0xbb 0xaf DINADF DINADF` | always | no | yes | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` |

- **dmp_set_fifo_rate / CFG_6** (img 3062): 12-byte trailer written unconditionally with the rate: {DINAFE, DINAF2, DINAAB, 0xc4, DINAAA, DINAF1, DINADF, DINADF, 0xBB, 0xAF, DINADF, DINADF}. In the mlsdk lineage CFG_6 is the 1-byte FIFO-interrupt point (fe = interrupt on packet).

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_fifo_rate` | D_0_22 | 534 | BE16 = DMP_SAMPLE_RATE(200)/rate - 1 (FIFO rate divider) | always | `00 05` |
| 1024 | mlsdk/mlFIFO.c | `inv_set_fifo_rate` | KEY_D_0_22 (D_0_22) | 22 | BE16 fifoRate divider (output every fifoRate+1 samples) | requested_sensors has DMP | `00 00` |
| 1923 | mlsdk/mlFIFO.c | `inv_set_fifo_rate` | KEY_D_0_22 (D_0_22) | 534 | BE16 fifoRate divider (output every fifoRate+1 samples) | requested_sensors has DMP | `00 00` |
| 1024 | mlsdk/mlFIFO.c | `inv_state_change_fifo` | KEY_D_1_178 (D_1_178) | 434 | BE16 signed = -((50 / sample_step_ms) + 1) | DMP start/state change | `00 00` |
| 1923 | mlsdk/mlFIFO.c | `inv_state_change_fifo` | KEY_D_1_178 (D_1_178) | 434 | BE16 signed = -((50 / sample_step_ms) + 1) | DMP start/state change | `00 00` |
| 1024 | mlsdk/mlFIFO.c | `inv_state_change_fifo` | KEY_D_1_128 (D_1_128) | 400 | BE32 = min(0x20000000*pi/(fifo_rate+1), 0x40000000) | INV_STATE_DMP_STARTED | `00 00 00 00` |
| 1923 | mlsdk/mlFIFO.c | `inv_state_change_fifo` | KEY_D_1_128 (D_1_128) | 400 | BE32 = min(0x20000000*pi/(fifo_rate+1), 0x40000000) | INV_STATE_DMP_STARTED | `00 00 00 00` |
| 1929 | i2cdev/6Axis_MotionApps20.cpp | `dmpInitialize` | D_0_22 (bank 2 offset 0x16) (D_0_22) | 534 | 2 bytes {0x00, MPU6050_DMP_FIFO_RATE_DIVISOR=0x01} | always | `00 01` |

## Interrupts

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_interrupt_mode` | CFG_FIFO_ON_EVENT | 2690 | continuous | `d8 b1 b9 f3 8b a3 91 b6 09 b4 d9` |  | DMP_INT_CONTINUOUS | yes | yes | `d8 b1 b9 f3 8b a3 91 b6 09 b4 d9` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_interrupt_mode` | CFG_FIFO_ON_EVENT | 2690 | gesture | `da b1 b9 f3 8b a3 91 b6 da b4 da` |  | DMP_INT_GESTURE | no | no | `d8 b1 b9 f3 8b a3 91 b6 09 b4 d9` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_ANDROID_ORIENT_INT | 1853 | enable | `d9` |  | DMP_FEATURE_ANDROID_ORIENT | no | no | `d8` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_ANDROID_ORIENT_INT | 1853 | disable | `d8` |  | otherwise | yes | yes | `d8` |
| 1024 | mlsdk/ml.c | `inv_set_motion_interrupt` | KEY_CFG_7 (CFG_7) | 564 | on | `fe` | `DINAFE` | on=1 | no |  | `d8` |
| 1024 | mlsdk/ml.c | `inv_set_motion_interrupt` | KEY_CFG_7 (CFG_7) | 564 | off | `d8` | `DINAD8` | on=0 | yes |  | `d8` |
| 1923 | mlsdk/ml.c | `inv_set_motion_interrupt` | KEY_CFG_7 (CFG_7) | 1014 | on | `fe` | `DINAFE` | on=1 | no |  | `d8` |
| 1923 | mlsdk/ml.c | `inv_set_motion_interrupt` | KEY_CFG_7 (CFG_7) | 1014 | off | `d8` | `DINAD8` | on=0 | yes |  | `d8` |
| 1024 | mlsdk/ml.c | `inv_set_fifo_interrupt` | KEY_CFG_6 (CFG_6) | 823 | on | `fe` | `DINAFE` | on=1 | no |  | `d8` |
| 1024 | mlsdk/ml.c | `inv_set_fifo_interrupt` | KEY_CFG_6 (CFG_6) | 823 | off | `d8` | `DINAD8` | on=0 | yes |  | `d8` |
| 1923 | mlsdk/ml.c | `inv_set_fifo_interrupt` | KEY_CFG_6 (CFG_6) | 1920 | on | `fe` | `DINAFE` | on=1 | no |  | `d8` |
| 1923 | mlsdk/ml.c | `inv_set_fifo_interrupt` | KEY_CFG_6 (CFG_6) | 1920 | off | `d8` | `DINAD8` | on=0 | yes |  | `d8` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_display_orient_interrupt_dmp` | KEY_CFG_DISPLAY_ORIENT_INT | - | on | `f4 41` |  | on | - |  | - |
| 2639 | hh/inv_mpu_misc.c | `inv_set_display_orient_interrupt_dmp` | KEY_CFG_DISPLAY_ORIENT_INT | - | off | `d8 d8` |  | !on | - |  | - |
| 2639 | hh/inv_mpu_misc.c | `inv_set_interrupt_on_gesture_event` | KEY_CFG_FIFO_INT (CFG_FIFO_INT) | 2362 | gesture_only | `a3` |  | on | no |  | `fe` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_interrupt_on_gesture_event` | KEY_CFG_FIFO_INT (CFG_FIFO_INT) | 2362 | every_packet | `fe` |  | !on | yes |  | `fe` |

- **dmp_set_interrupt_mode / CFG_FIFO_ON_EVENT** (img 3062): 11-byte block. Continuous = interrupt every FIFO period; gesture = interrupt only on tap/orient event. Differences at bytes 0, 8, 10: d8/09/d9 vs da/da/da.
- **dmp_enable_feature / CFG_ANDROID_ORIENT_INT** (img 3062): Android-orientation interrupt: d9 enable, d8 disable (d8/d9/da appear to be a family of 1-byte conditional/branch-ish opcodes).
- **inv_set_motion_interrupt / KEY_CFG_7** (img 1024): Motion/no-motion interrupt: DINAFE (0xfe) on, DINAD8 (0xd8) off.
- **inv_set_motion_interrupt / KEY_CFG_7** (img 1923): Motion/no-motion interrupt: DINAFE (0xfe) on, DINAD8 (0xd8) off.
- **inv_set_fifo_interrupt / KEY_CFG_6** (img 1024): "Enable generation of the DMP interrupt when a FIFO packet is ready": DINAFE on, DINAD8 off.
- **inv_set_fifo_interrupt / KEY_CFG_6** (img 1923): "Enable generation of the DMP interrupt when a FIFO packet is ready": DINAFE on, DINAD8 off.
- **inv_set_display_orient_interrupt_dmp / KEY_CFG_DISPLAY_ORIENT_INT** (img 2639): Display-orientation interrupt: on f4 41; off d8 d8. Key NOT in hammerhead dmpDefaultMPU6050.c table (unresolvable -> driver would log "key not local").
- **inv_set_interrupt_on_gesture_event / KEY_CFG_FIFO_INT** (img 2639): FIFO interrupt: a3 = interrupt only on gesture event (suppress per-packet int); fe = interrupt on every FIFO packet.

## Feature enable/disable

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_20 | 2224 | tap_enable | `f8` |  | DMP_FEATURE_TAP | no | no | `d8` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | CFG_20 | 2224 | tap_disable | `d8` |  | otherwise | yes | yes | `d8` |

- **dmp_enable_feature / CFG_20** (img 3062): "Enable tap." 0xf8 enables tap detection; 0xd8 disables.

## Gyro calibration / bias

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_gyro_cal` | CFG_MOTION_BIAS | 1208 | enable | `b8 aa b3 8d b4 98 0d 35 5d` |  | enable=1 | yes | yes | `b8 aa b3 8d b4 98 0d 35 5d` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_gyro_cal` | CFG_MOTION_BIAS | 1208 | disable | `b8 aa aa aa b0 88 c3 c5 c7` |  | enable=0 | no | no | `b8 aa b3 8d b4 98 0d 35 5d` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_turn_on_bias_from_no_motion` | KEY_CFG_MOTION_BIAS (CFG_MOTION_BIAS) | 1023 | on | `0d 35 5d` | `0x0d DINA35 0x5d` | always | yes |  | `0d 35 5d` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_turn_off_bias_from_no_motion` | KEY_CFG_MOTION_BIAS (CFG_MOTION_BIAS) | 1023 | off | `98 98 98` | `DINA90+8 DINA90+8 DINA90+8` | always | no |  | `0d 35 5d` |
| 1024 | mlsdk/ml.c | `inv_set_bias_update` | KEY_FCFG_5 (FCFG_5) | 942 | bias_from_lpf | `82 2d 55 7d` | `DINA80+2 DINA2D DINA55 DINA7D` | bias_mode & INV_BIAS_FROM_LPF | no |  | `87 2d 35 3d` |
| 1024 | mlsdk/ml.c | `inv_set_bias_update` | KEY_FCFG_5 (FCFG_5) | 942 | no_lpf | `87 2d 35 3d` | `DINA80+7 DINA2D DINA35 DINA3D` | otherwise | yes |  | `87 2d 35 3d` |
| 1923 | mlsdk/ml.c | `inv_set_bias_update` | KEY_FCFG_5 (FCFG_5) | 1030 | bias_from_lpf | `82 2d 55 7d` | `DINA80+2 DINA2D DINA55 DINA7D` | bias_mode & INV_BIAS_FROM_LPF | no |  | `87 2d 35 3d` |
| 1923 | mlsdk/ml.c | `inv_set_bias_update` | KEY_FCFG_5 (FCFG_5) | 1030 | no_lpf | `87 2d 35 3d` | `DINA80+7 DINA2D DINA35 DINA3D` | otherwise | yes |  | `87 2d 35 3d` |
| 1024 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_FCFG_6 (FCFG_6) | 996 | pause | `a3` | `DINAA0+3` | before reading D_1_244 | no |  | `af` |
| 1024 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_FCFG_6 (FCFG_6) | 996 | resume | `af` | `DINAA0+15` | after reading | yes |  | `af` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_FCFG_6 (FCFG_6) | 954 | pause | `a3` | `DINAA0+3` | before reading D_1_244 | no |  | `af` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_FCFG_6 (FCFG_6) | 954 | resume | `af` | `DINAA0+15` | after reading | yes |  | `af` |

- **dmp_enable_gyro_cal / CFG_MOTION_BIAS** (img 3062): "After eight seconds of no motion, the DMP will compute gyro biases and subtract them from the quaternion output." 9 bytes; enable and disable share prefix b8 aa, differ in bytes 2-8: b3 8d b4 98 0d 35 5d vs aa aa b0 88 c3 c5 c7. mlsdk Mantis writes only the 3-byte core 0d 35 5d / 98 98 98.
- **inv_turn_on_bias_from_no_motion / KEY_CFG_MOTION_BIAS** (img 1923): "Turns on the feature to compute gyro bias from No Motion" - 3-byte core 0d 35 5d (same as bytes 6-8 of eMD enable block).
- **inv_turn_off_bias_from_no_motion / KEY_CFG_MOTION_BIAS** (img 1923): Turns off no-motion bias: DINA90+8 x3 (0x98 0x98 0x98).
- **inv_set_bias_update / KEY_FCFG_5** (img 1024): Bias-from-LPF selector: LPF -> DINA80+2, DINA2D, DINA55, DINA7D; else DINA80+7, DINA2D, DINA35, DINA3D.
- **inv_set_bias_update / KEY_FCFG_5** (img 1923): Bias-from-LPF selector: LPF -> DINA80+2, DINA2D, DINA55, DINA7D; else DINA80+7, DINA2D, DINA35, DINA3D.
- **inv_update_bias / KEY_FCFG_6** (img 1024): Around reading the 12-byte no-motion bias (KEY_D_1_244): write DINAA0+3 (a3) before the read, DINAA0+15 (af) after - i.e. a3 pauses/skips the updater, af restores it.
- **inv_update_bias / KEY_FCFG_6** (img 1923): Around reading the 12-byte no-motion bias (KEY_D_1_244): write DINAA0+3 (a3) before the read, DINAA0+15 (af) after - i.e. a3 pauses/skips the updater, af restores it.

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_enable_feature` | D_0_104 | 104 | BE32 GYRO_SF = 46850825*200/DMP_SAMPLE_RATE (= 46850825 = 0x02CAE309) "integration scale factor" | always | `02 ca e3 09` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_gyro_bias` | D_EXT_GYRO_BIAS_X | 976 | BE32 = (bias_q16[body X] * GYRO_SF) >> 30 | always; body-axis remapped via dmp.orient | `00 00 00 00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_gyro_bias` | D_EXT_GYRO_BIAS_Y | 980 | BE32 = (bias_q16[body Y] * GYRO_SF) >> 30 | always; body-axis remapped via dmp.orient | `00 00 00 00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_gyro_bias` | D_EXT_GYRO_BIAS_Z | 984 | BE32 = (bias_q16[body Z] * GYRO_SF) >> 30 | always; body-axis remapped via dmp.orient | `00 00 00 00` |
| 1024 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_DMP_PREVPTAT (DMP_PREVPTAT) | 256 | 2 bytes = raw MPUREG_TEMP_OUT_H/L at time of bias capture | bias from no motion | `fb 00` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_update_bias` | KEY_DMP_PREVPTAT (DMP_PREVPTAT) | 256 | 2 bytes = raw MPUREG_TEMP_OUT_H/L at time of bias capture | bias from no motion | `fb 00` |
| 1024 | mlsdk/mlBiasNoMotion.c | `inv_update_bias (read)` | KEY_D_1_244 (D_1_244) | 500 | READ 12 bytes: 3 x BE32 gyro bias computed by DMP (no-motion) | bias from no motion | `00 00 03 65 00 00 00 99 00 00 02 f5` |
| 1923 | mlsdk/mlBiasNoMotion.c | `inv_update_bias (read)` | KEY_D_1_244 (D_1_244) | 500 | READ 12 bytes: 3 x BE32 gyro bias computed by DMP (no-motion) | bias from no motion | `00 2f 70 6d 00 00 05 ae 00 0c 02 d0` |
| 1923 | mlsdk/mlBiasNoMotion.c | `MLPollMotionStatus (read)` | KEY_D_2_96 (D_2_96) | 608 | READ 12 bytes: 3 x BE32 gyro bias (6050 build) | motionFlag > 0 | `00 00 00 01 00 00 00 02 00 00 00 00` |
| 1024 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_D_0_104 (D_0_104) | 104 | BE32 gyro_sf = gyro_sens * 767603923 / 2^30 | always | `02 ca e3 09` |
| 1923 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_D_0_104 (D_0_104) | 104 | BE32 gyro_sf = gyro_sens * 767603923 / 2^30 | always | `02 ca e3 09` |
| 1024 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_D_0_24 (D_0_24) | 24 | BE32 = 23832619764371 / gyro_sens | always | `00 03 77 8e` |
| 1923 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_D_0_24 (D_0_24) | 536 | BE32 = 23832619764371 / gyro_sens | always | `00 00 0c 00` |
| 1024 | mlsdk/ml.c | `inv_set_dead_zone` | KEY_D_0_163 (D_0_163) | 163 | 1 byte: 0x08 if INV_DEAD_ZONE; else 0x02 if BIAS_FROM_LPF (3050 build only) else 0 | always | `00` |
| 1923 | mlsdk/ml.c | `inv_set_dead_zone` | KEY_D_0_163 (D_0_163) | 163 | 1 byte: 0x08 if INV_DEAD_ZONE; else 0x02 if BIAS_FROM_LPF (3050 build only) else 0 | always | `00` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_gyro_sf_dmp` | KEY_D_0_104 (D_0_104) | 104 | BE32 gyro_sf = q30_mult(0x03e80000, DMP_TAP_SCALE*(sample_div+1)) | tap enable | `02 ca e3 09` |

## Orientation / sign (chip-to-body)

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_1 | 1062 | identity | `4c cd 6c` | `DINA4C DINACD DINA6C` | orient=0x88 (X<-X, Y<-Y, Z<-Z) | no | yes | `c5 cd c7` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_1 | 1062 | rule | `4c cd 6c` | `DINA4C DINACD DINA6C` | general: [gyro_axes[o&3], gyro_axes[(o>>3)&3], gyro_axes[(o>>6)&3]] | no | yes | `c5 cd c7` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_2 | 1066 | identity | `0c c9 2c` | `DINA0C DINAC9 DINA2C` | orient=0x88 | yes | yes | `0c c9 2c` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_3 | 1088 | all_positive | `36 56 76` | `DINA36 DINA56 DINA76` | no negation | yes | yes | `36 56 76` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_3 | 1088 | all_negated | `37 57 77` | `DINA36|1 DINA56|1 DINA76|1` | orient bits 2,5,8 set | no | no | `36 56 76` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_7 | 1073 | all_positive | `26 46 66` | `DINA26 DINA46 DINA66` | no negation | yes | yes | `26 46 66` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_orientation` | FCFG_7 | 1073 | all_negated | `27 47 67` | `DINA26|1 DINA46|1 DINA66|1` | orient bits 2,5,8 set | no | no | `26 46 66` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_2 (FCFG_2) | 895 | identity | `0c c9 2c` | `DINA0C DINAC9 DINA2C` | orient=0x88 | no |  | `c1 c9 c3` |
| 1024 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_2 (FCFG_2) | 872 | identity | `4c cd 6c` | `DINA4C DINACD DINA6C` | orient=0x88 | yes |  | `4c cd 6c` |
| 1024 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_7 (FCFG_7) | 930 | all_positive | `26 46 66` | `DINA26 DINA46 DINA66` | no negation | yes |  | `26 46 66` |
| 1024 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_7 (FCFG_7) | 930 | all_negated | `27 47 67` | `DINA26|1 DINA46|1 DINA66|1` | orient bits 2,5,8 | no |  | `26 46 66` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_7 (FCFG_7) | 902 | all_positive | `26 46 66` | `DINA26 DINA46 DINA66` | no negation, not B1_E1_5 | yes |  | `26 46 66` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_7 (FCFG_7) | 902 | all_positive_B1_E1_5 | `26 46 76` | `DINA26 DINA46 DINA76` | no negation, product B1_E1_5 | no |  | `26 46 66` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_FCFG_7 (FCFG_7) | 902 | all_negated | `27 47 67` | `DINA26|1 DINA46|1 DINA66|1` | orient bits 2,5,8 | no |  | `26 46 66` |
| 1923 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_1 (FCFG_1) | 891 | identity | `4c cd 6c` | `DINA4C DINACD DINA6C` | identity matrix | no |  | `c5 cd c7` |
| 1024 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_1 (FCFG_1) | 868 | identity | `c9 2c cb` | `DINAC9 DINA2C DINACB` | identity matrix | yes |  | `c9 2c cb` |
| 1024 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_3 (FCFG_3) | 936 | all_positive | `36 56 76` | `DINA36 DINA56 DINA76` | no negation | yes |  | `36 56 76` |
| 1024 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_3 (FCFG_3) | 936 | all_negated | `37 57 77` | `DINA36|1 DINA56|1 DINA76|1` | all rows negative | no |  | `36 56 76` |
| 1923 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_3 (FCFG_3) | 936 | all_positive | `36 56 76` | `DINA36 DINA56 DINA76` | no negation | yes |  | `36 56 76` |
| 1923 | mlsdk/ml.c | `inv_set_gyro_calibration` | KEY_FCFG_3 (FCFG_3) | 936 | all_negated | `37 57 77` | `DINA36|1 DINA56|1 DINA76|1` | all rows negative | no |  | `36 56 76` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x88_default | `cc cf 0e` | `DINACC DINACF DINA0E` | orient&0xdb default (typ. 0x88) | no |  | `ca cd cf` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x50 | `ce 0e cd` | `DINACE DINA0E DINACD` | orient&0xdb == 0x50 | no |  | `ca cd cf` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x81 | `ce cb 0e` | `DINACE DINACB DINA0E` | == 0x81 | no |  | `ca cd cf` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x11 | `cc 0e cb` | `DINACC DINA0E DINACB` | == 0x11 | no |  | `ca cd cf` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x42 | `0a cf cb` | `DINA0A DINACF DINACB` | == 0x42 | no |  | `ca cd cf` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ (FCFG_AZ) | 878 | 0x0a | `0a cb cd` | `DINA0A DINACB DINACD` | == 0x0a | no |  | `ca cd cf` |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x88_default | `cc cf 0e` | `DINACC DINACF DINA0E` | orient&0xdb default (typ. 0x88) | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x50 | `ce 0e cd` | `DINACE DINA0E DINACD` | orient&0xdb == 0x50 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x81 | `ce cb 0e` | `DINACE DINACB DINA0E` | == 0x81 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x11 | `cc 0e cb` | `DINACC DINA0E DINACB` | == 0x11 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x42 | `0a cf cb` | `DINA0A DINACF DINACB` | == 0x42 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | - | 0x0a | `0a cb cd` | `DINA0A DINACB DINACD` | == 0x0a | - |  | - |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x88_default | `c3 9e a9 3e 5e 7e c2 a9 99 fa cb 54 50 50 50 50 50 50 50 cd 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACB DINA54 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINACD DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | orient&0xdb default | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x50 | `c3 9e a9 3e 5e 7e c2 a9 99 fa cb cf 7c 78 78 78 78 78 78 78 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACB DINACF DINA7C DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x50 | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x81 | `c3 9e a9 3e 5e 7e c2 a9 99 fa 2c 28 28 28 28 28 28 28 cd cb 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINA2C DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINACD DINACB DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x81 | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x11 | `c3 9e a9 3e 5e 7e c2 a9 99 fa 2c 28 28 28 28 28 28 28 cb cf 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINA2C DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINACB DINACF DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x11 | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x42 | `c3 9e a9 3e 5e 7e c2 a9 99 fa cf cd 7c 78 78 78 78 78 78 78 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACF DINACD DINA7C DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x42 | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1024 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE (FCFG_FSCALE) | 877 | 0x0a | `c3 9e a9 3e 5e 7e c2 a9 99 fa cd 54 50 50 50 50 50 50 50 cf 97 fb a9 0e 0e 0e f9` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACD DINA54 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINACF DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x0a | no |  | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x88_default | `b5 9e a9 3e 5e 7e b4 a9 99 f2 cb 54 50 50 50 50 50 50 50 cd 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACB DINA54 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINACD DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | orient&0xdb default | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x50 | `b5 9e a9 3e 5e 7e b4 a9 99 f2 cb cf 7c 78 78 78 78 78 78 78 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACB DINACF DINA7C DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x50 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x81 | `b5 9e a9 3e 5e 7e b4 a9 99 f2 2c 28 28 28 28 28 28 28 cd cb 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINA2C DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINACD DINACB DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x81 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x11 | `b5 9e a9 3e 5e 7e b4 a9 99 f2 2c 28 28 28 28 28 28 28 cb cf 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINA2C DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINA28 DINACB DINACF DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x11 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x42 | `b5 9e a9 3e 5e 7e b4 a9 99 f2 cf cd 7c 78 78 78 78 78 78 78 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACF DINACD DINA7C DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA78 DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x42 | - |  | - |
| 1923 | mlsdk/ml.c | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | - | 0x0a | `b5 9e a9 3e 5e 7e b4 a9 99 f2 cd 54 50 50 50 50 50 50 50 cf 97 f3 a9 0e 0e 0e f1` | `DINAC3 DINA90+14 DINAA0+9 DINA3E DINA5E DINA7E DINAC2 DINAA0+9 DINA90+9 DINAF8+2 DINACD DINA54 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINA50 DINACF DINA90+7 DINAF8+3 DINAA0+9 DINA0E DINA0E DINA0E DINAF8+1` | == 0x0a | - |  | - |
| 2639 | hh/inv_mpu_misc.c | `inv_gyro_dmp_cal` | KEY_FCFG_1 (FCFG_1) | 1203 | identity | `4c cd 6c` | `DINA4C DINACD DINA6C` | orient=0x88 | no |  | `c5 cd c7` |
| 2639 | hh/inv_mpu_misc.c | `inv_gyro_dmp_cal` | KEY_FCFG_3 (FCFG_3) | 1228 | all_positive | `36 56 76` | `DINA36 DINA56 DINA76` | no negation | yes |  | `36 56 76` |
| 2639 | hh/inv_mpu_misc.c | `inv_gyro_dmp_cal` | KEY_FCFG_3 (FCFG_3) | 1228 | all_negated | `37 57 77` | `DINA36|1 DINA56|1 DINA76|1` | bits 2,5,8 | no |  | `36 56 76` |
| 2639 | hh/inv_mpu_misc.c | `inv_accel_dmp_cal` | KEY_FCFG_2 (FCFG_2) | 1207 | identity | `0c c9 2c` | `DINA0C DINAC9 DINA2C` | orient=0x88 | yes |  | `0c c9 2c` |
| 2639 | hh/inv_mpu_misc.c | `inv_accel_dmp_cal` | KEY_FCFG_7 (FCFG_7) | 1214 | all_positive | `26 46 66` | `DINA26 DINA46 DINA66` | no negation | yes |  | `26 46 66` |
| 2639 | hh/inv_mpu_misc.c | `inv_accel_dmp_cal` | KEY_FCFG_7 (FCFG_7) | 1214 | all_negated | `27 47 67` | `DINA26|1 DINA46|1 DINA66|1` | bits 2,5,8 | no |  | `26 46 66` |

- **dmp_set_orientation / FCFG_1** (img 3062): "Chip-to-body, axes only" gyro: byte i = gyro_axes[sel_i] with gyro_axes = {DINA4C, DINACD, DINA6C} (chip X/Y/Z); sel from orient bits [1:0],[4:3],[7:6].
- **dmp_set_orientation / FCFG_2** (img 3062): "Chip-to-body, axes only" accel: accel_axes = {DINA0C, DINAC9, DINA2C}.
- **dmp_set_orientation / FCFG_3** (img 3062): "Chip-to-body, sign only" gyro: gyro_sign = {DINA36, DINA56, DINA76}; low bit set (|1) negates that body axis (orient bits 2, 5, 8).
- **dmp_set_orientation / FCFG_7** (img 3062): "Chip-to-body, sign only" accel: accel_sign = {DINA26, DINA46, DINA66}; |1 negates.
- **inv_set_accel_calibration / KEY_FCFG_2** (img 1923): Accel axis select (6050 build): tmp = {DINA0C, DINAC9, DINA2C} indexed by orient scalar.
- **inv_set_accel_calibration / KEY_FCFG_2** (img 1024): Accel axis select (3050 build, external accel): tmp = {DINA4C, DINACD, DINA6C}.
- **inv_set_accel_calibration / KEY_FCFG_7** (img 1024): Accel sign: DINA26 DINA46 DINA66, |1 per negated axis.
- **inv_set_accel_calibration / KEY_FCFG_7** (img 1923): Accel sign (6050B1 build): DINA26 DINA46 then DINA76 if product key == MPU_PRODUCT_KEY_B1_E1_5 else DINA66; |1 per negated axis.
- **inv_set_gyro_calibration / KEY_FCFG_1** (img 1923): Gyro axis select (6050 build): tmpD/E/F = DINA4C/DINACD/DINA6C chosen by dominant matrix element per row.
- **inv_set_gyro_calibration / KEY_FCFG_1** (img 1024): Gyro axis select (3050 build): tmpD/E/F = DINAC9/DINA2C/DINACB.
- **inv_set_gyro_calibration / KEY_FCFG_3** (img 1024): Gyro sign: DINA36 DINA56 DINA76; |1 when the dominant matrix element for that row is negative.
- **inv_set_gyro_calibration / KEY_FCFG_3** (img 1923): Gyro sign: DINA36 DINA56 DINA76; |1 when the dominant matrix element for that row is negative.
- **inv_freescale_sensor_fusion_16bit / KEY_FCFG_AZ** (img 1024): Freescale MMA845X 16-bit accel axis fix-up; 3 bytes chosen by orient&0xdb.
- **inv_freescale_sensor_fusion_16bit / KEY_FCFG_AZ** (img 1923): Freescale MMA845X 16-bit accel axis fix-up; 3 bytes chosen by orient&0xdb.
- **inv_freescale_sensor_fusion_8bit / KEY_FCFG_FSCALE** (img 1024): Freescale MMA8450 8-bit accel: 27-byte routine = 10-byte prefix + 10-byte orient-specific body + 7-byte suffix (last byte F8+1 is "filler"). Bodies are runs of 7 repeated shift-ish opcodes (50/78/28) after a 54/7C/2C lead byte.
- **inv_freescale_sensor_fusion_8bit / KEY_FCFG_FSCALE** (img 1923): Freescale MMA8450 8-bit accel: 27-byte routine = 10-byte prefix + 10-byte orient-specific body + 7-byte suffix (last byte F8+1 is "filler"). Bodies are runs of 7 repeated shift-ish opcodes (50/78/28) after a 54/7C/2C lead byte.
- **inv_gyro_dmp_cal / KEY_FCFG_1** (img 2639): Gyro axis select: DINA4C/DINACD/DINA6C by orient bits.
- **inv_gyro_dmp_cal / KEY_FCFG_3** (img 2639): Gyro sign: DINA36/56/76, |1 negates.
- **inv_accel_dmp_cal / KEY_FCFG_2** (img 2639): Accel axis select: DINA0C/DINAC9/DINA2C.
- **inv_accel_dmp_cal / KEY_FCFG_7** (img 2639): Accel sign: DINA26/46/66, |1 negates.

## Tap

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | DMP_TAP_THX | 468 | BE16 = thresh(mg/ms)/200 * 16384/(fsr/2)  (X threshold) | axis bit set | `00 65` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | D_1_36 | 292 | BE16 = 0.75 * X threshold | axis bit set | `04 d6` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | DMP_TAP_THY | 472 | BE16 Y threshold | axis bit set | `00 64` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | D_1_40 | 296 | BE16 = 0.75 * Y threshold | axis bit set | `04 cc` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | DMP_TAP_THZ | 476 | BE16 Z threshold | axis bit set | `00 64` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_thresh` | D_1_44 | 300 | BE16 = 0.75 * Z threshold | axis bit set | `04 cc` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_axes` | D_1_72 | 328 | 1 byte bitmask: 0x30 = X, 0x0C = Y, 0x03 = Z | always | `00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_count` | D_1_79 | 335 | 1 byte = min_taps - 1 (1..4) | always | `00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_time` | DMP_TAPW_MIN | 478 | BE16 = ms / (1000/200) | always | `00 28` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_tap_time_multi` | D_1_218 | 474 | BE16 = ms / 5 | always | `03 e8` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_shake_reject_thresh` | D_1_92 | 348 | BE32 = (GYRO_SF/1000) * thresh_dps | always | `00 20 00 00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_shake_reject_time` | D_1_90 | 346 | BE16 = ms / 5 | always | `00 64` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_shake_reject_timeout` | D_1_88 | 344 | BE16 = ms / 5 | always | `00 05` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_tap_interrupt_dmp` | KEY_DMP_TAP_GATE (DMP_TAP_GATE) | 72 | BE16: 192 (00 c0) tap on, 128 (00 80) tap off | on/off | `00 00` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_tap_threshold_dmp` | KEY_DMP_TAP_THR_Z (DMP_TAP_THZ) | 88 | BE16 = threshold * (1+sample_div) * 0x2000 / DMP_PRECISION | always | `00 64` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_tap_threshold_dmp` | KEY_DMP_TAP_PREV_JERK_Z (DMP_TAP_PREV_JERK_Z) | 92 | BE16 = 3/4 * tap threshold | always | `04 cc` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_min_taps_dmp` | KEY_DMP_TAP_MIN_TAPS (DMP_TAP_MIN_TAPS) | 74 | BE16 = min_taps - 2 (DMP checks tap_count > min_taps, zero-based) | always | `00 00` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_tap_time_dmp` | KEY_DMP_TAPW_MIN (DMP_TAPW_MIN) | 90 | BE16 = ms / (sample_div+1) | always | `00 28` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_multiple_tap_time_dmp` | KEY_DMP_TAP_NEXT_TAP_THRES (DMP_TAP_NEXT_TAP_THRES) | 94 | BE16 = ms / (sample_div+1) | always | `03 e8` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_shake_reject_thresh_dmp` | KEY_DMP_TAP_SHAKE_REJECT (DMP_TAP_SHAKE_REJECT) | 80 | BE32 gyro threshold in chip units | always | `00 20 00 00` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_shake_reject_time_dmp` | KEY_DMP_TAP_SHAKE_COUNT_MAX (DMP_TAP_SHAKE_COUNT_MAX) | 84 | BE16 = ms / (sample_div+1) | always | `00 05` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_shake_reject_timeout_dmp` | KEY_DMP_TAP_SHAKE_TIMEOUT_MAX (DMP_TAP_SHAKE_TIMEOUT_MAX) | 86 | BE16 = ms / (sample_div+1) | always | `00 64` |

## Pedometer

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2639 | hh/inv_mpu_misc.c | `inv_enable_pedometer_interrupt` | KEY_CFG_PED_INT (CFG_PED_INT) | 2593 | enable | `f4 44 f1` |  | en | no |  | `f1 f1 f1` |
| 2639 | hh/inv_mpu_misc.c | `inv_enable_pedometer_interrupt` | KEY_CFG_PED_INT (CFG_PED_INT) | 2593 | disable | `f1 f1 f1` |  | !en | yes |  | `f1 f1 f1` |
| 2639 | hh/inv_mpu_misc.c | `inv_enable_pedometer` | KEY_CFG_PED_ENABLE (CFG_PED_ENABLE) | 2364 | enable | `f1` |  | en | yes |  | `f1` |
| 2639 | hh/inv_mpu_misc.c | `inv_enable_pedometer` | KEY_CFG_PED_ENABLE (CFG_PED_ENABLE) | 2364 | disable | `ff` |  | !en | no |  | `f1` |

- **inv_enable_pedometer_interrupt / KEY_CFG_PED_INT** (img 2639): Pedometer step interrupt: enable f4 44 f1; disable f1 f1 f1 (f1 = no-op filler; f4 44 = 2-byte op that raises the interrupt).
- **inv_enable_pedometer / KEY_CFG_PED_ENABLE** (img 2639): Pedometer enable: f1 (fall through into pedometer code) vs ff (skip/halt marker; ff also terminates every image).

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_pedometer_step_count` | D_PEDSTD_STEPCTR | 864 | BE32 step count (also read back by dmp_get_pedometer_step_count) | always | `00 00 00 00` |
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_pedometer_walk_time` | D_PEDSTD_TIMECTR | 964 | BE32 = walk_time_ms / 20 | always | `00 00 00 00` |

## Motion / no-motion

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1024 | mlsdk/ml.c | `inv_reset_motion` | KEY_CFG_18 (CFG_18) | 551 | motion | `da 0c d9` | `DINAD8+2 DINA0C DINAD8+1` | startup/resume | yes |  | `da 0c d9` |
| 1024 | mlsdk/mlBiasNoMotion.c | `MLPollMotionStatus` | KEY_CFG_18 (CFG_18) | 551 | enter_no_motion | `d9 0c da` | `DINAD8+1 DINA0C DINAD8+2` | motionFlag == motion_duration && state MOTION | no |  | `da 0c d9` |
| 1024 | mlsdk/mlBiasNoMotion.c | `MLPollMotionStatus` | KEY_CFG_18 (CFG_18) | 551 | enter_motion | `da 0c d9` | `DINAD8+2 DINA0C DINAD8+1` | motionFlag == 5 && state NO_MOTION | yes |  | `da 0c d9` |

- **inv_reset_motion / KEY_CFG_18** (img 1024): Reset to MOTION state (3050 only): DINAD8+2, DINA0C, DINAD8+1 = da 0c d9.
- **MLPollMotionStatus / KEY_CFG_18** (img 1024): 3050 motion state machine toggle: entering NO_MOTION writes d9 0c da; returning to MOTION writes da 0c d9 (swap of the d9/da bytes around DINA0C).

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 1024 | mlsdk/ml.c | `inv_reset_motion / inv_set_no_motion_time / MLPollMotionStatus` | KEY_D_1_106 (D_1_106) | 362 | BE16 motion_duration = time_s*200 (or 5 while in NO_MOTION on 3050) | always | `06 00` |
| 1923 | mlsdk/ml.c | `inv_reset_motion / inv_set_no_motion_time / MLPollMotionStatus` | KEY_D_1_106 (D_1_106) | 362 | BE16 motion_duration = time_s*200 (or 5 while in NO_MOTION on 3050) | always | `06 00` |
| 1024 | mlsdk/ml.c | `inv_reset_motion` | KEY_D_1_96 (D_1_96) | 352 | 8 zero bytes | reset | `00 00 00 00 00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_reset_motion` | KEY_D_1_96 (D_1_96) | 352 | 8 zero bytes | reset | `00 00 00 01 00 00 00 00` |
| 1024 | mlsdk/ml.c | `inv_reset_motion / inv_accel_compass_supervisor` | KEY_D_0_96 (D_0_96) | 96 | BE32 Q30: 0x40000000 (1.0) on reset; accSF accel sensor-fusion weight from supervisor | reset / when accSF changes | `00 3e 03 30` |
| 1923 | mlsdk/ml.c | `inv_reset_motion / inv_accel_compass_supervisor` | KEY_D_0_96 (D_0_96) | 96 | BE32 Q30: 0x40000000 (1.0) on reset; accSF accel sensor-fusion weight from supervisor | reset / when accSF changes | `00 3e 03 30` |
| 1024 | mlsdk/ml.c | `inv_set_no_motion_thresh` | KEY_D_1_108 (D_1_108) | 364 | BE32 = thresh^2 * 2.045 | always | `00 00 00 14` |
| 1923 | mlsdk/ml.c | `inv_set_no_motion_thresh` | KEY_D_1_108 (D_1_108) | 364 | BE32 = thresh^2 * 2.045 | always | `00 00 00 14` |
| 1024 | mlsdk/mlBiasNoMotion.c | `MLPollMotionStatus (read)` | KEY_D_1_98 (D_1_98) | 354 | READ BE16 motionFlag | poll | `00 00` |
| 1923 | mlsdk/mlBiasNoMotion.c | `MLPollMotionStatus (read)` | KEY_D_1_98 (D_1_98) | 354 | READ BE16 motionFlag | poll | `00 01` |

## Accel calibration

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 1024 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_D_1_152 (D_1_152) | 268 | 4 bytes zero-g offset: 80 00 80 00 for KXSD9, else 00 00 00 00 | key supported | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_D_1_152 (D_1_152) | 268 | 4 bytes zero-g offset: 80 00 80 00 for KXSD9, else 00 00 00 00 | key supported | `00 00 00 00` |
| 1024 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_D_0_108 (D_0_108) | 108 | BE16 = 2^30 / accel_sens | always | `3e 80` |
| 1923 | mlsdk/ml.c | `inv_set_accel_calibration` | KEY_D_0_108 (D_0_108) | 108 | BE16 = 2^30 / accel_sens | always | `3e 80` |
| 1024 | mlsdk/ml.c | `inv_apply_endian_accel` | KEY_D_1_236 (D_1_236) | 492 | 4 bytes: 00 40 00 00 for FS8/FS16 big-endian or little-endian secondary-bus accel; 00 00 40 00 for big-endian/primary | always | `00 40 00 00` |
| 1923 | mlsdk/ml.c | `inv_apply_endian_accel` | KEY_D_1_236 (D_1_236) | 492 | 4 bytes: 00 40 00 00 for FS8/FS16 big-endian or little-endian secondary-bus accel; 00 00 40 00 for big-endian/primary | always | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_mpu_6050_config` | KEY_D_ACT0 (D_ACT0) | 640 | BE32 from OTP accel trim byte | Mantis | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_mpu_6050_config` | KEY_D_ACSX (D_ACSX) | 644 | BE32 = orientation-rotated OTP accel scale trim * 2516582 | Mantis | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_mpu_6050_config` | KEY_D_ACSY (D_ACSY) | 648 | BE32 = orientation-rotated OTP accel scale trim * 2516582 | Mantis | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_mpu_6050_config` | KEY_D_ACSZ (D_ACSZ) | 652 | BE32 = orientation-rotated OTP accel scale trim * 2516582 | Mantis | `00 00 00 00` |

## Accel bias

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 3062 | emd/inv_mpu_dmp_motion_driver.c | `dmp_set_accel_bias` | D_ACCEL_BIAS | 660 | 3 x BE32 = (bias_q16 * (accel_sens<<15)) >> 30, X,Y,Z body frame | always | `00 00 00 00 00 00 00 00 00 00 00 00` |
| 2639 | hh/inv_mpu_misc.c | `inv_set_accel_bias_dmp` | KEY_D_ACCEL_BIAS (D_ACCEL_BIAS) | 660 | 3 x BE32 body-frame accel bias | always | `00 00 00 00 00 00 00 00 00 00 00 00` |

## Compass

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_00 (CPASS_MTX_00) | 576 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `40 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_01 (CPASS_MTX_01) | 580 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_02 (CPASS_MTX_02) | 584 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_10 (CPASS_MTX_10) | 588 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_11 (CPASS_MTX_11) | 592 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `40 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_12 (CPASS_MTX_12) | 596 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_20 (CPASS_MTX_20) | 600 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_21 (CPASS_MTX_21) | 604 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `00 00 00 00` |
| 1923 | mlsdk/ml.c | `inv_set_compass_calibration` | KEY_CPASS_MTX_22 (CPASS_MTX_22) | 700 | 4 bytes: 40 00 00 00 (+1), c0 00 00 00 (-1), 00 00 00 00 (0)  [Q30 sign in first byte] | per orientation matrix element | `40 00 00 00` |

## Quaternion seed

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 2639 | hh/inv_mpu_misc.c | `inv_six_q_write` | KEY_DMP_Q0 (D_FS_Q0) | 192 | 16 bytes: 4 x BE32 quaternion (Q30) written from sysfs six_axes_q_value | firmware loaded, DMP not enabled | `40 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00` |

## i2cdev MotionApps 4.1 dmpConfig (image 1962)

### Instruction sequences

| img | source | function | key (label) | addr | variant | bytes (hex) | mnemonics | condition | img default | dump3062 | image bytes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0x82 | 898 | config | `4c cd 6c` |  | always (startup) | no |  | `c5 cd c7` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0xb2 | 946 | config | `36 56 76` |  | always (startup) | yes |  | `36 56 76` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0x86 | 902 | config | `0c c9 2c` |  | always (startup) | yes |  | `0c c9 2c` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0x90 | 912 | config | `26 46 66` |  | always (startup) | yes |  | `26 46 66` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0x86 | 902 | config | `0c c9 2c 97 97 97` |  | always (startup) | yes |  | `0c c9 2c 97 97 97` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x04 offset 0x22 | 1058 | config | `0d 35 5d` |  | always (startup) | yes |  | `0d 35 5d` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x04 offset 0x29 | 1065 | config | `87 2d 35 3d` |  | always (startup) | yes |  | `87 2d 35 3d` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x62 | 1890 | config | `f1 20 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x9f | 1951 | config | `30` |  | always (startup) | no |  | `a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x67 | 1895 | config | `9a` |  | always (startup) | no |  | `95` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x68 | 1896 | config | `f1 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x62 | 1890 | config | `f1 20 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x83 | 1923 | config | `c2 ca c4 a3 a3 a3` |  | always (startup) | no |  | `a3 a3 a3 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0xa7 | 1959 | config | `fe` |  | always (startup) | no |  | `d8` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x62 | 1890 | config | `f1 20 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x67 | 1895 | config | `9a` |  | always (startup) | no |  | `95` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x68 | 1896 | config | `f1 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x8d | 1933 | config | `f1 28 30 38` |  | always (startup) | no |  | `f1 a3 a3 a3` |

- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x03 offset 0x82** (img 1962): i2cdev comment: FCFG_1 inv_set_gyro_calibration
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x03 offset 0xb2** (img 1962): i2cdev comment: FCFG_3 inv_set_gyro_calibration
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x03 offset 0x86** (img 1962): i2cdev comment: FCFG_2 inv_set_accel_calibration
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x03 offset 0x90** (img 1962): i2cdev comment: (labelled "continued FCFG_2"; by content this is FCFG_7 accel sign)
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x04 offset 0x22** (img 1962): i2cdev comment: CFG_MOTION_BIAS inv_turn_on_bias_from_no_motion
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x04 offset 0x29** (img 1962): i2cdev comment: FCFG_5 inv_set_bias_update
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x62** (img 1962): i2cdev comment: CFG_8 inv_send_quaternion
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x9f** (img 1962): i2cdev comment: CFG_16 inv_set_footer
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x67** (img 1962): i2cdev comment: CFG_GYRO_SOURCE inv_send_gyro
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x68** (img 1962): i2cdev comment: CFG_9 inv_send_gyro -> inv_construct3_fifo
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x83** (img 1962): i2cdev comment: ? (= CFG_EXTERNAL pattern: first 3 external elements on)
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0xa7** (img 1962): i2cdev comment: ? (= CFG_6 fifo interrupt on, by mlsdk analogy)
- **dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig) / bank 0x07 offset 0x8d** (img 1962): i2cdev comment: ??? CFG_12 inv_send_mag -> inv_construct3_fifo

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0xec | 748 | 00 47 7d 1a (4 bytes literal) | always (startup) | `00 47 78 a2` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x00 offset 0x68 | 104 | 02 ca e3 09 (4 bytes literal) | always (startup) | `02 ca e3 09` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x01 offset 0x0c | 268 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x00 offset 0x6c | 108 | 40 00 (2 bytes literal) | always (startup) | `3e 80` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x40 | 576 | 00 00 00 00 (4 bytes literal) | always (startup) | `40 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x44 | 580 | 40 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x48 | 584 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x4c | 588 | 40 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x50 | 592 | 00 00 00 00 (4 bytes literal) | always (startup) | `40 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x54 | 596 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x58 | 600 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x5c | 604 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0xbc | 700 | c0 00 00 00 (4 bytes literal) | always (startup) | `40 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x01 offset 0xec | 492 | 00 00 40 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x00 offset 0xa3 | 163 | 00 (1 bytes literal) | always (startup) | `00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x0c | 524 | 00 00 00 00 (4 bytes literal) | always (startup) | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x02 offset 0x16 | 534 | 00 03 (2 bytes literal) | always (startup) | `00 00` |

## i2cdev MotionApps 4.1 dmpUpdates (image 1962)

### Data writes (establish data addresses)

| img | source | function | key (label) | addr | format / value | condition | image bytes now |
|---|---|---|---|---|---|---|---|
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0xb2 | 434 | ff f5 (2 bytes literal) | startup sequence | `00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x90 | 400 | 0a 0d 97 c0 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x00 offset 0xa3 | 163 | 00 (1 bytes literal) | startup sequence | `00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x04 offset 0x29 | 1065 | 87 2d 35 3d (4 bytes literal) | startup sequence | `87 2d 35 3d` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x6a | 362 | 06 00 (2 bytes literal) | startup sequence | `06 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x60 | 352 | 00 00 00 00 00 00 00 00 (8 bytes literal) | startup sequence | `00 00 00 01 00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x00 offset 0x60 | 96 | 40 00 00 00 (4 bytes literal) | startup sequence | `00 3e 03 30` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0x60 | 608 | 00 00 00 00 00 00 00 00 00 00 00 00 (12 bytes literal) | startup sequence | `00 00 00 01 00 00 00 02 00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x08 | 264 | 01 20 (2 bytes literal) | startup sequence | `00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x0a | 266 | 00 4e (2 bytes literal) | startup sequence | `00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x01 offset 0x02 | 258 | fe b3 (2 bytes literal) | startup sequence | `00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0x6c | 620 | 00 00 00 00 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0x6c | 620 | fa fe 00 00 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0x60 | 608 | ff ff cb 4d 00 01 08 c1 ff ff bc 2c (12 bytes literal) | startup sequence | `00 00 00 01 00 00 00 02 00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0xf4 | 756 | 00 00 00 00 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0xf8 | 760 | 00 00 00 00 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x02 offset 0xfc | 764 | 00 00 00 00 (4 bytes literal) | startup sequence | `00 00 00 00` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x00 offset 0x60 | 96 | 40 00 00 00 (4 bytes literal) | startup sequence | `00 3e 03 30` |
| 1962 | i2cdev/9Axis_MotionApps41.cpp | `dmpInitialize -> writeMemoryBlock(dmpUpdates[i])` | bank 0x00 offset 0x60 | 96 | 00 40 00 00 (4 bytes literal) | startup sequence | `00 3e 03 30` |

## Observations from the image-default check

Config points where the shipped image holds **none** of the driver variants (i.e. the factory placeholder differs from every value a driver ever writes):

| img | function | key | addr | image bytes | driver variants |
|---|---|---|---|---|---|
| 3062 | `dmp_enable_feature` | CFG_27 | 2742 | `a3` | gesture_off=`d8`; gesture_on=`20` |
| 3062 | `dmp_set_fifo_rate` | CFG_6 | 2753 | `a3 a3 a3 a3 a3 a3 a3 a3 a3 a3 a3 a3` | regs_end=`fe f2 ab c4 aa f1 df df bb af df df` |
| 3062 | `dmp_set_orientation` | FCFG_1 | 1062 | `c5 cd c7` | identity=`4c cd 6c`; rule=`4c cd 6c` |
| 1024 | `inv_send_packet_number` | KEY_CFG_23 | 814 | `a3` | off=`fb`; on=`28` |
| 1923 | `inv_send_packet_number` | KEY_CFG_23 | 1911 | `a3` | off=`f3`; on=`28` |
| 1923 | `inv_set_accel_calibration` | KEY_FCFG_2 | 895 | `c1 c9 c3` | identity=`0c c9 2c` |
| 1923 | `inv_set_gyro_calibration` | KEY_FCFG_1 | 891 | `c5 cd c7` | identity=`4c cd 6c` |
| 1024 | `inv_freescale_sensor_fusion_16bit` | KEY_FCFG_AZ | 878 | `ca cd cf` | 0x0a=`0a cb cd`; 0x11=`cc 0e cb`; 0x42=`0a cf cb`; 0x50=`ce 0e cd`; 0x81=`ce cb 0e`; 0x88_default=`cc cf 0e` |
| 1024 | `inv_freescale_sensor_fusion_8bit` | KEY_FCFG_FSCALE | 877 | `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd` | 0x0a=`c3 9e a9 3e 5e 7e c2 a9 99 fa cd 54 50 50 50 50 50 50 50 cf 97 fb a9 0e 0e 0e f9`; 0x11=`c3 9e a9 3e 5e 7e c2 a9 99 fa 2c 28 28 28 28 28 28 28 cb cf 97 fb a9 0e 0e 0e f9`; 0x42=`c3 9e a9 3e 5e 7e c2 a9 99 fa cf cd 7c 78 78 78 78 78 78 78 97 fb a9 0e 0e 0e f9`; 0x50=`c3 9e a9 3e 5e 7e c2 a9 99 fa cb cf 7c 78 78 78 78 78 78 78 97 fb a9 0e 0e 0e f9`; 0x81=`c3 9e a9 3e 5e 7e c2 a9 99 fa 2c 28 28 28 28 28 28 28 cd cb 97 fb a9 0e 0e 0e f9`; 0x88_default=`c3 9e a9 3e 5e 7e c2 a9 99 fa cb 54 50 50 50 50 50 50 50 cd 97 fb a9 0e 0e 0e f9` |
| 1923 | `inv_turn_off_bias_from_no_motion` | KEY_CFG_MOTION_BIAS | 1023 | `0d 35 5d` | off=`98 98 98` |
| 2639 | `inv_gyro_dmp_cal` | KEY_FCFG_1 | 1203 | `c5 cd c7` | identity=`4c cd 6c` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x03 offset 0x82 | 898 | `c5 cd c7` | config=`4c cd 6c` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x62 | 1890 | `f1 a3 a3 a3 a3` | config=`f1 20 28 30 38` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x9f | 1951 | `a3` | config=`30` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x67 | 1895 | `95` | config=`9a` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x68 | 1896 | `f1 a3 a3 a3` | config=`f1 28 30 38` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x83 | 1923 | `a3 a3 a3 a3 a3 a3` | config=`c2 ca c4 a3 a3 a3` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0xa7 | 1959 | `d8` | config=`fe` |
| 1962 | `dmpInitialize -> writeProgDMPConfigurationSet(dmpConfig)` | bank 0x07 offset 0x8d | 1933 | `f1 a3 a3 a3` | config=`f1 28 30 38` |

Readings (function names only; no further semantics asserted):

- **FCFG_1 (gyro axis select) ships as `c5 cd c7` in images 1923, 2639, 3062 and 1962**, while every driver writes `4c cd 6c` for identity (`DINA4C/DINACD/DINA6C`). The middle byte is shared, so `c5`<->`4c` and `c7`<->`6c` are the placeholder-vs-live pair for the X and Z slots. Likewise **FCFG_2 (accel axis select) ships as `c1 c9 c3` in 1923** where drivers write `0c c9 2c`; the 1962 image already contains `0c c9 2c`. Pattern: placeholder `c1/c3/c5/c7` <-> live `0c/2c/4c/6c`, with `c9`/`cd` unchanged.
- **CFG_23 (packet-number slot) ships as `a3`** in 1024 and 1923; drivers only ever write `28` (on) or `DINAF8+3` (`fb`/`f3`, off). So `a3` and `f3`/`fb` are both used as "emit nothing here" fillers in the same slot.
- **CFG_27 ships as `a3` in the pristine eMD 3062**; eMD writes `20` (send gesture word) or `d8`. The i2cdev dump holds `d8`.
- **CFG_6 in the pristine eMD 3062 is twelve `a3` bytes**; `dmp_set_fifo_rate` overwrites it with `fe f2 ab c4 aa f1 df df bb af df df` (the dump holds that). In the mlsdk images the same-named label CFG_6 is a 1-byte interrupt toggle (`fe`/`d8`) - same name, different role across lineages.
- **CFG_16 (footer) ships as `a3`** (footer off) in 1024, 1923 and 1962; drivers write `30` to add the 2-byte footer. **CFG_GYRO_SOURCE ships as `95`** (`DINA90+5`, gyro-from-quaternion) in 1024, 1923 and 1962, although i2cdev MotionApps 4.1 writes `9a` (raw) into it. **CFG_6/CFG_7 (fifo/motion interrupt) ship as `d8`** (off) in 1024 and 1923.
- **1024 FCFG_AZ (878) and FCFG_FSCALE (877) overlap by one byte**; the 1024 image there reads `a5 ca cd cf c3 9e a9 3e 5e 7e 85 a5 1a 3e 5e c2 a5 99 fb 08 34 5c f9 a9 c9 cb cd`, which shares the `c3 9e a9 3e 5e 7e ... c2 ... 99 fb ... f9` skeleton of the 27-byte `inv_freescale_sensor_fusion_8bit` routine but with a different body - so the shipped bytes are the non-Freescale default of that routine.
- The i2cdev **3062 dump** differs from the pristine eMD image at exactly the config points eMD touches: CFG_8 = `20 28 30 38` (6-axis quat on), CFG_15 = `a3 c0 c8 c2 c4 cc c6 a3 a3 a3` (raw accel + gyro out), CFG_27 = `d8`, CFG_6 = fifo-rate trailer, FCFG_1 = `4c cd 6c`; CFG_GYRO_RAW_DATA stays `b2 8b b6 9b` (cal gyro), CFG_LP_QUAT stays `8b 8b 8b 8b`, CFG_MOTION_BIAS stays enable (`b8 aa b3 8d ...`). That is consistent with i2cdev 6.12 running `dmp_enable_feature(6X_LP_QUAT|SEND_RAW_ACCEL|SEND_CAL_GYRO|GYRO_CAL)`.
- Image defaults that **do** match a driver variant everywhere checked: CFG_MOTION_BIAS = enable (3062: 9-byte enable block; 1923: `0d 35 5d`), FCFG_3/FCFG_7 = all-positive signs, FCFG_5 = no-LPF `87 2d 35 3d`, FCFG_6 = `af` (resume), CFG_LP_QUAT = disabled `8b x4`, CFG_8/CFG_12/CFG_9/CFG_1/CFG_TAP0/TAP4/CFG_15/CFG_EXTERNAL = all elements off (`a3` fill), CFG_FIFO_ON_EVENT = continuous, CFG_ANDROID_ORIENT_INT = `d8` (off), CFG_20 = `d8` (tap off), and in 2639: CFG_PED_ENABLE = `f1` (pedometer enabled), CFG_PED_INT = `f1 f1 f1` (step interrupt off), CFG_FIFO_INT = `fe` (interrupt on every packet).

## Keys that could not be resolved

- image 1024: `KEY_P_EIS_FIFO_XSHIFT` (used by `inv_send_eis`) - not present in that image's key table
- image 1923: `KEY_FCFG_AZ` (used by `inv_freescale_sensor_fusion_16bit`) - not present in that image's key table
- image 1923: `KEY_FCFG_FSCALE` (used by `inv_freescale_sensor_fusion_8bit`) - not present in that image's key table
- image 1923: `KEY_P_EIS_FIFO_XSHIFT` (used by `inv_send_eis`) - not present in that image's key table
- image 2639: `KEY_CFG_DISPLAY_ORIENT_INT` (used by `inv_set_display_orient_interrupt_dmp`) - not present in that image's key table

## Symbol tables

All `#define`d addresses per image (config labels, D_* data addresses, code labels, and the lineage's `dmpmap.h` DMP_* names). Sorted by address.

### Image 3062

| name | addr | name | addr | name | addr | name | addr |
|---|---|---|---|---|---|---|---|
| `DMP_PTAT` | 0 | `DMP_XGYR` | 2 | `DMP_YGYR` | 4 | `DMP_ZGYR` | 6 |
| `DMP_XACC` | 8 | `DMP_YACC` | 10 | `DMP_ZACC` | 12 | `DMP_ADC1` | 14 |
| `DMP_ADC2` | 16 | `DMP_ADC3` | 18 | `DMP_BIASUNC` | 20 | `DMP_FIFORT` | 22 |
| `DMP_INVGSFH` | 24 | `DMP_INVGSFL` | 26 | `DMP_1H` | 28 | `DMP_1L` | 30 |
| `DMP_BLPFSTCH` | 32 | `DMP_BLPFSTCL` | 34 | `DMP_BLPFSXH` | 36 | `D_0_36` | 36 |
| `DMP_BLPFSXL` | 38 | `DMP_BLPFSYH` | 40 | `DMP_BLPFSYL` | 42 | `DMP_BLPFSZH` | 44 |
| `DMP_BLPFSZL` | 46 | `DMP_BLPFMTC` | 48 | `D_TILT0_H` | 48 | `DMP_SMC` | 50 |
| `D_TILT0_L` | 50 | `DMP_BLPFMXH` | 52 | `D_0_52` | 52 | `D_TILT1_H` | 52 |
| `DMP_BLPFMXL` | 54 | `D_TILT1_L` | 54 | `DMP_BLPFMYH` | 56 | `D_TILT2_H` | 56 |
| `DMP_BLPFMYL` | 58 | `D_TILT2_L` | 58 | `DMP_BLPFMZH` | 60 | `D_TILT3_H` | 60 |
| `DMP_BLPFMZL` | 62 | `D_TILT3_L` | 62 | `DMP_BLPFC` | 64 | `DMP_SMCTH` | 66 |
| `DMP_0H2` | 68 | `DMP_0L2` | 70 | `DMP_BERR2H` | 72 | `DMP_BERR2L` | 74 |
| `DMP_BERR2NH` | 76 | `D_ORIENT_GAP` | 76 | `DMP_SMCINC` | 78 | `DMP_ANGVBXH` | 80 |
| `DMP_ANGVBXL` | 82 | `DMP_ANGVBYH` | 84 | `DMP_ANGVBYL` | 86 | `DMP_ANGVBZH` | 88 |
| `DMP_ANGVBZL` | 90 | `DMP_BERR1H` | 92 | `DMP_BERR1L` | 94 | `DMP_ATCH` | 96 |
| `D_0_96` | 96 | `DMP_BIASUNCSF` | 98 | `DMP_ACT2H` | 100 | `DMP_ACT2L` | 102 |
| `DMP_GSFH` | 104 | `D_0_104` | 104 | `DMP_GSFL` | 106 | `DMP_GH` | 108 |
| `D_0_108` | 108 | `DMP_GL` | 110 | `DMP_0_5H` | 112 | `DMP_0_5L` | 114 |
| `DMP_0_0H` | 116 | `DMP_0_0L` | 118 | `DMP_1_0H` | 120 | `DMP_1_0L` | 122 |
| `DMP_1_5H` | 124 | `DMP_1_5L` | 126 | `DMP_TMP1AH` | 128 | `DMP_TMP1AL` | 130 |
| `DMP_TMP2AH` | 132 | `DMP_TMP2AL` | 134 | `DMP_TMP3AH` | 136 | `DMP_TMP3AL` | 138 |
| `DMP_TMP4AH` | 140 | `DMP_TMP4AL` | 142 | `DMP_XACCW` | 144 | `DMP_TMP5` | 146 |
| `DMP_XACCB` | 148 | `DMP_TMP8` | 150 | `DMP_YACCB` | 152 | `DMP_TMP9` | 154 |
| `DMP_ZACCB` | 156 | `DMP_TMP10` | 158 | `DMP_DZH` | 160 | `DMP_DZL` | 162 |
| `D_0_163` | 163 | `DMP_XGCH` | 164 | `DMP_XGCL` | 166 | `DMP_YGCH` | 168 |
| `DMP_YGCL` | 170 | `DMP_ZGCH` | 172 | `DMP_ZGCL` | 174 | `DMP_YACCW` | 176 |
| `DMP_TMP7` | 178 | `DMP_AFB1H` | 180 | `DMP_AFB1L` | 182 | `DMP_AFB2H` | 184 |
| `DMP_AFB2L` | 186 | `DMP_MAGFBH` | 188 | `D_0_188` | 188 | `DMP_MAGFBL` | 190 |
| `DMP_QT1H` | 192 | `D_0_192` | 192 | `DMP_QT1L` | 194 | `DMP_QT2H` | 196 |
| `DMP_QT2L` | 198 | `DMP_QT3H` | 200 | `DMP_QT3L` | 202 | `DMP_QT4H` | 204 |
| `DMP_QT4L` | 206 | `DMP_CTRL1H` | 208 | `DMP_CTRL1L` | 210 | `DMP_CTRL2H` | 212 |
| `DMP_CTRL2L` | 214 | `DMP_CTRL3H` | 216 | `DMP_CTRL3L` | 218 | `DMP_CTRL4H` | 220 |
| `DMP_CTRL4L` | 222 | `DMP_CTRLS1` | 224 | `D_0_224` | 224 | `DMP_CTRLSF1` | 226 |
| `DMP_CTRLS2` | 228 | `D_0_228` | 228 | `DMP_CTRLSF2` | 230 | `DMP_CTRLS3` | 232 |
| `D_0_232` | 232 | `DMP_CTRLSFNLL` | 234 | `DMP_CTRLS4` | 236 | `D_0_236` | 236 |
| `DMP_CTRLSFNL2` | 238 | `DMP_CTRLSFNL` | 240 | `DMP_TMP30` | 242 | `DMP_CTRLSFJT` | 244 |
| `DMP_TMP31` | 246 | `DMP_TMP11` | 248 | `DMP_CTRLSF2_2` | 250 | `DMP_TMP12` | 252 |
| `DMP_CTRLSF1_2` | 254 | `DMP_PREVPTAT` | 256 | `DMP_ACCZB` | 258 | `D_1_2` | 258 |
| `D_1_4` | 260 | `DMP_ACCXB` | 264 | `D_1_8` | 264 | `DMP_ACCYB` | 266 |
| `D_1_10` | 266 | `D_1_152` | 268 | `DMP_1HB` | 272 | `DMP_1LB` | 274 |
| `DMP_0H` | 276 | `DMP_0L` | 278 | `DMP_ASR22H` | 280 | `D_1_24` | 280 |
| `DMP_ASR22L` | 282 | `DMP_ASR6H` | 284 | `D_1_28` | 284 | `DMP_ASR6L` | 286 |
| `DMP_TMP13` | 288 | `DMP_TMP14` | 290 | `DMP_FINTXH` | 292 | `D_1_36` | 292 |
| `DMP_FINTXL` | 294 | `DMP_FINTYH` | 296 | `D_1_40` | 296 | `DMP_FINTYL` | 298 |
| `DMP_FINTZH` | 300 | `D_1_44` | 300 | `DMP_FINTZL` | 302 | `DMP_TMP1BH` | 304 |
| `DMP_TMP1BL` | 306 | `DMP_TMP2BH` | 308 | `DMP_TMP2BL` | 310 | `DMP_TMP3BH` | 312 |
| `DMP_TMP3BL` | 314 | `DMP_TMP4BH` | 316 | `DMP_TMP4BL` | 318 | `DMP_STXG` | 320 |
| `DMP_ZCTXG` | 322 | `DMP_STYG` | 324 | `DMP_ZCTYG` | 326 | `DMP_STZG` | 328 |
| `D_1_72` | 328 | `DMP_ZCTZG` | 330 | `D_1_74` | 330 | `DMP_CTRLSFJT2` | 332 |
| `DMP_CTRLSFJTCNT` | 334 | `D_1_79` | 335 | `DMP_PVXG` | 336 | `DMP_TMP15` | 338 |
| `DMP_PVYG` | 340 | `DMP_TMP16` | 342 | `DMP_PVZG` | 344 | `D_1_88` | 344 |
| `DMP_TMP17` | 346 | `D_1_90` | 346 | `D_1_92` | 348 | `DMP_MNMFLAGH` | 352 |
| `D_1_96` | 352 | `DMP_MNMFLAGL` | 354 | `D_1_98` | 354 | `DMP_MNMTMH` | 356 |
| `DMP_MNMTML` | 358 | `DMP_MNMTMTHRH` | 360 | `DMP_MNMTMTHRL` | 362 | `D_1_106` | 362 |
| `DMP_MNMTHRH` | 364 | `D_1_108` | 364 | `DMP_MNMTHRL` | 366 | `DMP_ACCQD4H` | 368 |
| `D_1_112` | 368 | `DMP_ACCQD4L` | 370 | `DMP_ACCQD5H` | 372 | `DMP_ACCQD5L` | 374 |
| `DMP_ACCQD6H` | 376 | `DMP_ACCQD6L` | 378 | `DMP_ACCQD7H` | 380 | `DMP_ACCQD7L` | 382 |
| `DMP_ACCQD0H` | 384 | `DMP_ACCQD0L` | 386 | `DMP_ACCQD1H` | 388 | `DMP_ACCQD1L` | 390 |
| `DMP_ACCQD2H` | 392 | `DMP_ACCQD2L` | 394 | `DMP_ACCQD3H` | 396 | `DMP_ACCQD3L` | 398 |
| `DMP_XN2H` | 400 | `D_1_128` | 400 | `DMP_XN2L` | 402 | `DMP_XN1H` | 404 |
| `DMP_XN1L` | 406 | `DMP_YN2H` | 408 | `DMP_YN2L` | 410 | `DMP_YN1H` | 412 |
| `DMP_YN1L` | 414 | `DMP_YH` | 416 | `D_1_160` | 416 | `DMP_YL` | 418 |
| `DMP_B0H` | 420 | `DMP_B0L` | 422 | `DMP_A1H` | 424 | `DMP_A1L` | 426 |
| `DMP_A2H` | 428 | `DMP_A2L` | 430 | `DMP_SEM1` | 432 | `D_1_176` | 432 |
| `DMP_FIFOCNT` | 434 | `D_1_178` | 434 | `DMP_SH_TH_X` | 436 | `DMP_PACKET` | 438 |
| `DMP_SH_TH_Y` | 440 | `DMP_FOOTER` | 442 | `DMP_SH_TH_Z` | 444 | `DMP_TEMP29` | 448 |
| `DMP_TEMP30` | 450 | `DMP_XACCB_PRE` | 452 | `DMP_XACCB_PREL` | 454 | `DMP_YACCB_PRE` | 456 |
| `DMP_YACCB_PREL` | 458 | `DMP_ZACCB_PRE` | 460 | `DMP_ZACCB_PREL` | 462 | `DMP_TMP22` | 464 |
| `DMP_TAP_TIMER` | 466 | `DMP_TAP_THX` | 468 | `DMP_TAP_THY` | 472 | `D_1_218` | 474 |
| `DMP_TAP_THZ` | 476 | `DMP_TAPW_MIN` | 478 | `DMP_TMP25` | 480 | `DMP_TMP26` | 482 |
| `DMP_TMP27` | 484 | `DMP_TMP28` | 486 | `DMP_ORIENT` | 488 | `D_1_232` | 488 |
| `DMP_THRSH` | 490 | `DMP_ENDIANH` | 492 | `D_1_236` | 492 | `DMP_ENDIANL` | 494 |
| `DMP_BLPFNMTCH` | 496 | `D_1_240` | 496 | `DMP_BLPFNMTCL` | 498 | `DMP_BLPFNMXH` | 500 |
| `D_1_244` | 500 | `DMP_BLPFNMXL` | 502 | `DMP_BLPFNMYH` | 504 | `DMP_BLPFNMYL` | 506 |
| `D_1_250` | 506 | `DMP_BLPFNMZH` | 508 | `D_1_252` | 508 | `DMP_BLPFNMZL` | 510 |
| `D_2_12` | 524 | `D_0_22` | 534 | `D_0_24` | 536 | `CPASS_BIAS_X` | 564 |
| `CPASS_BIAS_Y` | 568 | `CPASS_BIAS_Z` | 572 | `CPASS_MTX_00` | 576 | `CPASS_MTX_01` | 580 |
| `CPASS_MTX_02` | 584 | `CPASS_MTX_10` | 588 | `CPASS_MTX_11` | 592 | `CPASS_MTX_12` | 596 |
| `CPASS_MTX_20` | 600 | `CPASS_MTX_21` | 604 | `D_2_96` | 608 | `D_2_108` | 620 |
| `D_ACT0` | 640 | `D_ACSX` | 644 | `D_ACSY` | 648 | `D_ACSZ` | 652 |
| `D_ACCEL_BIAS` | 660 | `CPASS_MTX_22` | 700 | `D_2_208` | 720 | `FLICK_MSG` | 724 |
| `FLICK_COUNTER` | 728 | `FLICK_LOWER` | 732 | `D_2_224` | 736 | `D_2_236` | 748 |
| `FLICK_UPPER` | 748 | `D_2_244` | 756 | `D_2_248` | 760 | `D_2_252` | 764 |
| `D_PEDSTD_BP_B` | 796 | `D_PEDSTD_SB` | 808 | `D_PEDSTD_TIML` | 810 | `D_PEDSTD_SB_TIME` | 812 |
| `D_PEDSTD_TIMH` | 814 | `D_PEDSTD_BP_A4` | 832 | `D_PEDSTD_BP_A3` | 836 | `D_PEDSTD_BP_A2` | 840 |
| `D_PEDSTD_BP_A1` | 844 | `D_PEDSTD_STEPCTR` | 864 | `D_PEDSTD_INT_THRSH` | 872 | `D_PEDSTD_CLIP` | 876 |
| `D_PEDSTD_HP_A` | 888 | `D_PEDSTD_HP_B` | 892 | `D_PEDSTD_PEAK` | 916 | `D_PEDSTD_PEAKTHRSH` | 920 |
| `D_PEDSTD_DECI` | 928 | `D_PEDSTD_TIMECTR` | 964 | `D_EXT_GYRO_BIAS_X` | 976 | `D_HOST_NO_MOT` | 976 |
| `D_EXT_GYRO_BIAS_Y` | 980 | `D_EXT_GYRO_BIAS_Z` | 984 | `D_AUTH_OUT` | 992 | `D_AUTH_IN` | 996 |
| `D_AUTH_A` | 1000 | `D_AUTH_B` | 1004 | `CFG_DR_INT` | 1029 | `CFG_AUTH` | 1035 |
| `FCFG_1` | 1062 | `FCFG_2` | 1066 | `FCFG_7` | 1073 | `FCFG_3` | 1088 |
| `FCFG_6` | 1106 | `CFG_EXT_GYRO_BIAS` | 1189 | `CFG_7` | 1205 | `CFG_MOTION_BIAS` | 1208 |
| `X_GRT_Y_TMP` | 1358 | `SKIP_X_GRT_Y_TMP` | 1359 | `X_GRT_Y_TMP2` | 1379 | `END_COMPARE_Y_X_TMP` | 1407 |
| `X_GRT_Y` | 1408 | `END_COMPARE_Y_X_TMP3` | 1434 | `SKIP_END_COMPARE` | 1435 | `END_COMPARE_Y_X_TMP2` | 1455 |
| `END_COMPARE_Y_X` | 1484 | `SWING_END_1` | 1550 | `SKIP_SWING_END_1` | 1551 | `SWING_END_2` | 1565 |
| `SKIP_SWING_END_2` | 1566 | `SWING_END_3` | 1587 | `SKIP_SWING_END_3` | 1588 | `SWING_END_4` | 1616 |
| `TILTL75_START` | 1643 | `TILTL75_END` | 1669 | `TILTG75_START` | 1672 | `FLAT_STATE_END_TEMP` | 1683 |
| `FLAT_STATE_END` | 1713 | `END_PREDICTION_UPDATE` | 1761 | `UPDATE_PROP_ROT` | 1835 | `DO_NOT_UPDATE_PROP_ROT` | 1839 |
| `CFG_ANDROID_ORIENT_INT` | 1853 | `END_ORIENT_TEMP` | 1866 | `END_ORIENT` | 1884 | `CFG_20` | 2224 |
| `TEMPLABEL` | 2324 | `CFG_FLICK_IN` | 2573 | `CGNOTICE_INTR` | 2620 | `CFG_FIFO_ON_EVENT` | 2690 |
| `CFG_LP_QUAT` | 2712 | `CFG_8` | 2718 | `CFG_GYRO_RAW_DATA` | 2722 | `CFG_15` | 2727 |
| `CFG_27` | 2742 | `CFG_23` | 2745 | `CFG_16` | 2746 | `CFG_6` | 2753 |

### Image 1024

| name | addr | name | addr | name | addr | name | addr |
|---|---|---|---|---|---|---|---|
| `DMP_PTAT` | 0 | `DMP_XGYR` | 2 | `DMP_YGYR` | 4 | `DMP_ZGYR` | 6 |
| `DMP_XACC` | 8 | `DMP_YACC` | 10 | `DMP_ZACC` | 12 | `DMP_ADC1` | 14 |
| `DMP_ADC2` | 16 | `DMP_ADC3` | 18 | `DMP_BIASUNC` | 20 | `DMP_FIFORT` | 22 |
| `D_0_22` | 22 | `DMP_INVGSFH` | 24 | `D_0_24` | 24 | `DMP_INVGSFL` | 26 |
| `DMP_1H` | 28 | `DMP_1L` | 30 | `DMP_BLPFSTCH` | 32 | `DMP_BLPFSTCL` | 34 |
| `DMP_BLPFSXH` | 36 | `D_0_36` | 36 | `DMP_BLPFSXL` | 38 | `DMP_BLPFSYH` | 40 |
| `DMP_BLPFSYL` | 42 | `DMP_BLPFSZH` | 44 | `DMP_BLPFSZL` | 46 | `DMP_BLPFMTC` | 48 |
| `DMP_SMC` | 50 | `DMP_BLPFMXH` | 52 | `D_0_52` | 52 | `DMP_BLPFMXL` | 54 |
| `DMP_BLPFMYH` | 56 | `DMP_BLPFMYL` | 58 | `DMP_BLPFMZH` | 60 | `DMP_BLPFMZL` | 62 |
| `DMP_BLPFC` | 64 | `DMP_SMCTH` | 66 | `DMP_0H2` | 68 | `DMP_0L2` | 70 |
| `DMP_BERR2H` | 72 | `DMP_BERR2L` | 74 | `DMP_BERR2NH` | 76 | `DMP_SMCINC` | 78 |
| `DMP_ANGVBXH` | 80 | `DMP_ANGVBXL` | 82 | `DMP_ANGVBYH` | 84 | `DMP_ANGVBYL` | 86 |
| `DMP_ANGVBZH` | 88 | `DMP_ANGVBZL` | 90 | `DMP_BERR1H` | 92 | `DMP_BERR1L` | 94 |
| `DMP_ATCH` | 96 | `D_0_96` | 96 | `DMP_BIASUNCSF` | 98 | `DMP_ACT2H` | 100 |
| `DMP_ACT2L` | 102 | `DMP_GSFH` | 104 | `D_0_104` | 104 | `DMP_GSFL` | 106 |
| `DMP_GH` | 108 | `D_0_108` | 108 | `DMP_GL` | 110 | `DMP_0_5H` | 112 |
| `DMP_0_5L` | 114 | `DMP_0_0H` | 116 | `DMP_0_0L` | 118 | `DMP_1_0H` | 120 |
| `DMP_1_0L` | 122 | `DMP_1_5H` | 124 | `DMP_1_5L` | 126 | `DMP_TMP1AH` | 128 |
| `DMP_TMP1AL` | 130 | `DMP_TMP2AH` | 132 | `DMP_TMP2AL` | 134 | `DMP_TMP3AH` | 136 |
| `DMP_TMP3AL` | 138 | `DMP_TMP4AH` | 140 | `DMP_TMP4AL` | 142 | `DMP_XACCW` | 144 |
| `DMP_TMP5` | 146 | `DMP_XACCB` | 148 | `DMP_TMP8` | 150 | `DMP_YACCB` | 152 |
| `DMP_TMP9` | 154 | `DMP_ZACCB` | 156 | `DMP_TMP10` | 158 | `DMP_DZH` | 160 |
| `DMP_DZL` | 162 | `D_0_163` | 163 | `DMP_XGCH` | 164 | `DMP_XGCL` | 166 |
| `DMP_YGCH` | 168 | `DMP_YGCL` | 170 | `DMP_ZGCH` | 172 | `DMP_ZGCL` | 174 |
| `DMP_YACCW` | 176 | `DMP_TMP7` | 178 | `DMP_AFB1H` | 180 | `DMP_AFB1L` | 182 |
| `DMP_AFB2H` | 184 | `DMP_AFB2L` | 186 | `DMP_MAGFBH` | 188 | `D_0_188` | 188 |
| `DMP_MAGFBL` | 190 | `DMP_QT1H` | 192 | `D_0_192` | 192 | `DMP_QT1L` | 194 |
| `DMP_QT2H` | 196 | `DMP_QT2L` | 198 | `DMP_QT3H` | 200 | `DMP_QT3L` | 202 |
| `DMP_QT4H` | 204 | `DMP_QT4L` | 206 | `DMP_CTRL1H` | 208 | `DMP_CTRL1L` | 210 |
| `DMP_CTRL2H` | 212 | `DMP_CTRL2L` | 214 | `DMP_CTRL3H` | 216 | `DMP_CTRL3L` | 218 |
| `DMP_CTRL4H` | 220 | `DMP_CTRL4L` | 222 | `DMP_CTRLS1` | 224 | `D_0_224` | 224 |
| `DMP_CTRLSF1` | 226 | `DMP_CTRLS2` | 228 | `D_0_228` | 228 | `DMP_CTRLSF2` | 230 |
| `DMP_CTRLS3` | 232 | `D_0_232` | 232 | `DMP_CTRLSFNLL` | 234 | `DMP_CTRLS4` | 236 |
| `D_0_236` | 236 | `DMP_CTRLSFNL2` | 238 | `DMP_CTRLSFNL` | 240 | `DMP_TMP30` | 242 |
| `DMP_CTRLSFJT` | 244 | `DMP_TMP31` | 246 | `DMP_TMP11` | 248 | `DMP_CTRLSF2_2` | 250 |
| `DMP_TMP12` | 252 | `DMP_CTRLSF1_2` | 254 | `DMP_PREVPTAT` | 256 | `DMP_ACCZB` | 258 |
| `D_1_2` | 258 | `D_1_4` | 260 | `DMP_ACCXB` | 264 | `D_1_8` | 264 |
| `DMP_ACCYB` | 266 | `D_1_10` | 266 | `D_1_152` | 268 | `DMP_1HB` | 272 |
| `DMP_1LB` | 274 | `DMP_0H` | 276 | `DMP_0L` | 278 | `DMP_ASR22H` | 280 |
| `D_1_24` | 280 | `DMP_ASR22L` | 282 | `DMP_ASR6H` | 284 | `D_1_28` | 284 |
| `DMP_ASR6L` | 286 | `DMP_TMP13` | 288 | `DMP_TMP14` | 290 | `DMP_FINTXH` | 292 |
| `DMP_FINTXL` | 294 | `DMP_FINTYH` | 296 | `DMP_FINTYL` | 298 | `DMP_FINTZH` | 300 |
| `DMP_FINTZL` | 302 | `DMP_TMP1BH` | 304 | `DMP_TMP1BL` | 306 | `DMP_TMP2BH` | 308 |
| `DMP_TMP2BL` | 310 | `DMP_TMP3BH` | 312 | `DMP_TMP3BL` | 314 | `DMP_TMP4BH` | 316 |
| `DMP_TMP4BL` | 318 | `DMP_STXG` | 320 | `DMP_ZCTXG` | 322 | `DMP_STYG` | 324 |
| `DMP_ZCTYG` | 326 | `DMP_STZG` | 328 | `DMP_ZCTZG` | 330 | `DMP_CTRLSFJT2` | 332 |
| `DMP_CTRLSFJTCNT` | 334 | `DMP_PVXG` | 336 | `DMP_TMP15` | 338 | `DMP_PVYG` | 340 |
| `DMP_TMP16` | 342 | `DMP_PVZG` | 344 | `DMP_TMP17` | 346 | `D_1_92` | 348 |
| `DMP_MNMFLAGH` | 352 | `D_1_96` | 352 | `DMP_MNMFLAGL` | 354 | `D_1_98` | 354 |
| `DMP_MNMTMH` | 356 | `DMP_MNMTML` | 358 | `DMP_MNMTMTHRH` | 360 | `DMP_MNMTMTHRL` | 362 |
| `D_1_106` | 362 | `DMP_MNMTHRH` | 364 | `D_1_108` | 364 | `DMP_MNMTHRL` | 366 |
| `DMP_ACCQD4H` | 368 | `D_1_112` | 368 | `DMP_ACCQD4L` | 370 | `DMP_ACCQD5H` | 372 |
| `DMP_ACCQD5L` | 374 | `DMP_ACCQD6H` | 376 | `DMP_ACCQD6L` | 378 | `DMP_ACCQD7H` | 380 |
| `DMP_ACCQD7L` | 382 | `DMP_ACCQD0H` | 384 | `DMP_ACCQD0L` | 386 | `DMP_ACCQD1H` | 388 |
| `DMP_ACCQD1L` | 390 | `DMP_ACCQD2H` | 392 | `DMP_ACCQD2L` | 394 | `DMP_ACCQD3H` | 396 |
| `DMP_ACCQD3L` | 398 | `DMP_XN2H` | 400 | `D_1_128` | 400 | `DMP_XN2L` | 402 |
| `DMP_XN1H` | 404 | `DMP_XN1L` | 406 | `DMP_YN2H` | 408 | `DMP_YN2L` | 410 |
| `DMP_YN1H` | 412 | `DMP_YN1L` | 414 | `DMP_YH` | 416 | `DMP_YL` | 418 |
| `DMP_B0H` | 420 | `DMP_B0L` | 422 | `DMP_A1H` | 424 | `D_1_168` | 424 |
| `DMP_A1L` | 426 | `DMP_A2H` | 428 | `DMP_A2L` | 430 | `D_1_175` | 431 |
| `DMP_SEM1` | 432 | `DMP_FIFOCNT` | 434 | `D_1_178` | 434 | `DMP_SH_TH_X` | 436 |
| `DMP_PACKET` | 438 | `DMP_SH_TH_Y` | 440 | `DMP_FOOTER` | 442 | `DMP_SH_TH_Z` | 444 |
| `DMP_TEMP29` | 448 | `DMP_TEMP30` | 450 | `DMP_XACCB_PRE` | 452 | `DMP_XACCB_PREL` | 454 |
| `DMP_YACCB_PRE` | 456 | `DMP_YACCB_PREL` | 458 | `DMP_ZACCB_PRE` | 460 | `DMP_ZACCB_PREL` | 462 |
| `DMP_TMP22` | 464 | `DMP_TAP_TIMER` | 466 | `DMP_TAP_THX` | 468 | `DMP_TAP_THY` | 472 |
| `DMP_TAP_THZ` | 476 | `DMP_TAPW_MIN` | 478 | `DMP_TMP25` | 480 | `DMP_TMP26` | 482 |
| `DMP_TMP27` | 484 | `DMP_TMP28` | 486 | `DMP_ORIENT` | 488 | `DMP_THRSH` | 490 |
| `DMP_ENDIANH` | 492 | `D_1_236` | 492 | `DMP_ENDIANL` | 494 | `DMP_BLPFNMTCH` | 496 |
| `DMP_BLPFNMTCL` | 498 | `DMP_BLPFNMXH` | 500 | `D_1_244` | 500 | `DMP_BLPFNMXL` | 502 |
| `DMP_BLPFNMYH` | 504 | `DMP_BLPFNMYL` | 506 | `DMP_BLPFNMZH` | 508 | `DMP_BLPFNMZL` | 510 |
| `CFG_3` | 515 | `CFG_3B` | 517 | `CFG_3C` | 519 | `CFG_3D` | 521 |
| `CFG_4` | 526 | `CFG_18` | 551 | `CFG_7` | 564 | `CFG_TAP_JERK` | 639 |
| `CFG_20` | 645 | `CFG_TAP_QUANTIZE` | 647 | `CFG_TAP_SAVE_ACCB` | 687 | `CFG_24` | 699 |
| `CFG_25` | 703 | `CFG_26` | 707 | `CFG_ORIENT_1` | 713 | `CFG_ORIENT_IRQ_1` | 715 |
| `CFG_ORIENT_2` | 733 | `CFG_ORIENT_IRQ_2` | 738 | `CFG_ORIENT_IRQ_3` | 743 | `CFG_5` | 749 |
| `CFG_8` | 772 | `CFG_GYRO_SOURCE` | 777 | `CFG_9` | 778 | `CFG_1` | 783 |
| `CFG_14` | 790 | `CFG_15` | 790 | `CFG_12` | 797 | `CFG_21` | 802 |
| `CFG_TAP0` | 802 | `CFG_TAP1` | 804 | `CFG_TAP2` | 805 | `CFG_TAP3` | 806 |
| `CFG_TAP4` | 808 | `CFG_TAP5` | 809 | `CFG_TAP6` | 810 | `CFG_TAP7` | 811 |
| `CFG_23` | 814 | `CFG_16` | 815 | `CFG_TAP_CLEAR_STICKY` | 817 | `CFG_6` | 823 |
| `FCFG_ACCEL_INIT` | 831 | `FCFG_4` | 857 | `FCFG_1` | 868 | `FCFG_2` | 872 |
| `FCFG_FSCALE` | 877 | `FCFG_AZ` | 878 | `FCFG_ACCEL_INPUT` | 904 | `FCFG_7` | 930 |
| `FCFG_3` | 936 | `FCFG_5` | 942 | `CFG_ACCEL_FILTER` | 968 | `FCFG_6` | 996 |

### Image 1923

| name | addr | name | addr | name | addr | name | addr |
|---|---|---|---|---|---|---|---|
| `DMP_PTAT` | 0 | `DMP_XGYR` | 2 | `DMP_YGYR` | 4 | `DMP_ZGYR` | 6 |
| `DMP_XACC` | 8 | `DMP_YACC` | 10 | `DMP_ZACC` | 12 | `DMP_ADC1` | 14 |
| `DMP_ADC2` | 16 | `DMP_ADC3` | 18 | `DMP_BIASUNC` | 20 | `DMP_FIFORT` | 22 |
| `DMP_INVGSFH` | 24 | `DMP_INVGSFL` | 26 | `DMP_1H` | 28 | `DMP_1L` | 30 |
| `DMP_BLPFSTCH` | 32 | `DMP_BLPFSTCL` | 34 | `DMP_BLPFSXH` | 36 | `D_0_36` | 36 |
| `DMP_BLPFSXL` | 38 | `DMP_BLPFSYH` | 40 | `DMP_BLPFSYL` | 42 | `DMP_BLPFSZH` | 44 |
| `DMP_BLPFSZL` | 46 | `DMP_BLPFMTC` | 48 | `DMP_SMC` | 50 | `DMP_BLPFMXH` | 52 |
| `D_0_52` | 52 | `DMP_BLPFMXL` | 54 | `DMP_BLPFMYH` | 56 | `DMP_BLPFMYL` | 58 |
| `DMP_BLPFMZH` | 60 | `DMP_BLPFMZL` | 62 | `DMP_BLPFC` | 64 | `DMP_SMCTH` | 66 |
| `DMP_0H2` | 68 | `DMP_0L2` | 70 | `DMP_BERR2H` | 72 | `DMP_BERR2L` | 74 |
| `DMP_BERR2NH` | 76 | `DMP_SMCINC` | 78 | `DMP_ANGVBXH` | 80 | `DMP_ANGVBXL` | 82 |
| `DMP_ANGVBYH` | 84 | `DMP_ANGVBYL` | 86 | `DMP_ANGVBZH` | 88 | `DMP_ANGVBZL` | 90 |
| `DMP_BERR1H` | 92 | `DMP_BERR1L` | 94 | `DMP_ATCH` | 96 | `D_0_96` | 96 |
| `DMP_BIASUNCSF` | 98 | `DMP_ACT2H` | 100 | `DMP_ACT2L` | 102 | `DMP_GSFH` | 104 |
| `D_0_104` | 104 | `DMP_GSFL` | 106 | `DMP_GH` | 108 | `D_0_108` | 108 |
| `DMP_GL` | 110 | `DMP_0_5H` | 112 | `DMP_0_5L` | 114 | `DMP_0_0H` | 116 |
| `DMP_0_0L` | 118 | `DMP_1_0H` | 120 | `DMP_1_0L` | 122 | `DMP_1_5H` | 124 |
| `DMP_1_5L` | 126 | `DMP_TMP1AH` | 128 | `DMP_TMP1AL` | 130 | `DMP_TMP2AH` | 132 |
| `DMP_TMP2AL` | 134 | `DMP_TMP3AH` | 136 | `DMP_TMP3AL` | 138 | `DMP_TMP4AH` | 140 |
| `DMP_TMP4AL` | 142 | `DMP_XACCW` | 144 | `DMP_TMP5` | 146 | `DMP_XACCB` | 148 |
| `DMP_TMP8` | 150 | `DMP_YACCB` | 152 | `DMP_TMP9` | 154 | `DMP_ZACCB` | 156 |
| `DMP_TMP10` | 158 | `DMP_DZH` | 160 | `DMP_DZL` | 162 | `D_0_163` | 163 |
| `DMP_XGCH` | 164 | `DMP_XGCL` | 166 | `DMP_YGCH` | 168 | `DMP_YGCL` | 170 |
| `DMP_ZGCH` | 172 | `DMP_ZGCL` | 174 | `DMP_YACCW` | 176 | `DMP_TMP7` | 178 |
| `DMP_AFB1H` | 180 | `DMP_AFB1L` | 182 | `DMP_AFB2H` | 184 | `DMP_AFB2L` | 186 |
| `DMP_MAGFBH` | 188 | `D_0_188` | 188 | `DMP_MAGFBL` | 190 | `DMP_QT1H` | 192 |
| `D_0_192` | 192 | `DMP_QT1L` | 194 | `DMP_QT2H` | 196 | `DMP_QT2L` | 198 |
| `DMP_QT3H` | 200 | `DMP_QT3L` | 202 | `DMP_QT4H` | 204 | `DMP_QT4L` | 206 |
| `DMP_CTRL1H` | 208 | `DMP_CTRL1L` | 210 | `DMP_CTRL2H` | 212 | `DMP_CTRL2L` | 214 |
| `DMP_CTRL3H` | 216 | `DMP_CTRL3L` | 218 | `DMP_CTRL4H` | 220 | `DMP_CTRL4L` | 222 |
| `DMP_CTRLS1` | 224 | `D_0_224` | 224 | `DMP_CTRLSF1` | 226 | `DMP_CTRLS2` | 228 |
| `D_0_228` | 228 | `DMP_CTRLSF2` | 230 | `DMP_CTRLS3` | 232 | `D_0_232` | 232 |
| `DMP_CTRLSFNLL` | 234 | `DMP_CTRLS4` | 236 | `D_0_236` | 236 | `DMP_CTRLSFNL2` | 238 |
| `DMP_CTRLSFNL` | 240 | `DMP_TMP30` | 242 | `DMP_CTRLSFJT` | 244 | `DMP_TMP31` | 246 |
| `DMP_TMP11` | 248 | `DMP_CTRLSF2_2` | 250 | `DMP_TMP12` | 252 | `DMP_CTRLSF1_2` | 254 |
| `DMP_PREVPTAT` | 256 | `DMP_ACCZB` | 258 | `D_1_2` | 258 | `D_1_4` | 260 |
| `DMP_ACCXB` | 264 | `D_1_8` | 264 | `DMP_ACCYB` | 266 | `D_1_10` | 266 |
| `D_1_152` | 268 | `DMP_1HB` | 272 | `DMP_1LB` | 274 | `DMP_0H` | 276 |
| `DMP_0L` | 278 | `DMP_ASR22H` | 280 | `D_1_24` | 280 | `DMP_ASR22L` | 282 |
| `DMP_ASR6H` | 284 | `D_1_28` | 284 | `DMP_ASR6L` | 286 | `DMP_TMP13` | 288 |
| `DMP_TMP14` | 290 | `DMP_FINTXH` | 292 | `DMP_FINTXL` | 294 | `DMP_FINTYH` | 296 |
| `DMP_FINTYL` | 298 | `DMP_FINTZH` | 300 | `DMP_FINTZL` | 302 | `DMP_TMP1BH` | 304 |
| `DMP_TMP1BL` | 306 | `DMP_TMP2BH` | 308 | `DMP_TMP2BL` | 310 | `DMP_TMP3BH` | 312 |
| `DMP_TMP3BL` | 314 | `DMP_TMP4BH` | 316 | `DMP_TMP4BL` | 318 | `DMP_STXG` | 320 |
| `DMP_ZCTXG` | 322 | `DMP_STYG` | 324 | `DMP_ZCTYG` | 326 | `DMP_STZG` | 328 |
| `DMP_ZCTZG` | 330 | `DMP_CTRLSFJT2` | 332 | `DMP_CTRLSFJTCNT` | 334 | `DMP_PVXG` | 336 |
| `DMP_TMP15` | 338 | `DMP_PVYG` | 340 | `DMP_TMP16` | 342 | `DMP_PVZG` | 344 |
| `DMP_TMP17` | 346 | `D_1_92` | 348 | `DMP_MNMFLAGH` | 352 | `D_1_96` | 352 |
| `DMP_MNMFLAGL` | 354 | `D_1_98` | 354 | `DMP_MNMTMH` | 356 | `DMP_MNMTML` | 358 |
| `DMP_MNMTMTHRH` | 360 | `DMP_MNMTMTHRL` | 362 | `D_1_106` | 362 | `DMP_MNMTHRH` | 364 |
| `D_1_108` | 364 | `DMP_MNMTHRL` | 366 | `DMP_ACCQD4H` | 368 | `D_1_112` | 368 |
| `DMP_ACCQD4L` | 370 | `DMP_ACCQD5H` | 372 | `DMP_ACCQD5L` | 374 | `DMP_ACCQD6H` | 376 |
| `DMP_ACCQD6L` | 378 | `DMP_ACCQD7H` | 380 | `DMP_ACCQD7L` | 382 | `DMP_ACCQD0H` | 384 |
| `DMP_ACCQD0L` | 386 | `DMP_ACCQD1H` | 388 | `DMP_ACCQD1L` | 390 | `DMP_ACCQD2H` | 392 |
| `DMP_ACCQD2L` | 394 | `DMP_ACCQD3H` | 396 | `DMP_ACCQD3L` | 398 | `DMP_XN2H` | 400 |
| `D_1_128` | 400 | `DMP_XN2L` | 402 | `DMP_XN1H` | 404 | `DMP_XN1L` | 406 |
| `DMP_YN2H` | 408 | `DMP_YN2L` | 410 | `DMP_YN1H` | 412 | `DMP_YN1L` | 414 |
| `DMP_YH` | 416 | `DMP_YL` | 418 | `DMP_B0H` | 420 | `DMP_B0L` | 422 |
| `DMP_A1H` | 424 | `D_1_168` | 424 | `DMP_A1L` | 426 | `DMP_A2H` | 428 |
| `DMP_A2L` | 430 | `D_1_175` | 431 | `DMP_SEM1` | 432 | `DMP_FIFOCNT` | 434 |
| `D_1_178` | 434 | `DMP_SH_TH_X` | 436 | `DMP_PACKET` | 438 | `DMP_SH_TH_Y` | 440 |
| `DMP_FOOTER` | 442 | `DMP_SH_TH_Z` | 444 | `DMP_TEMP29` | 448 | `DMP_TEMP30` | 450 |
| `DMP_XACCB_PRE` | 452 | `DMP_XACCB_PREL` | 454 | `DMP_YACCB_PRE` | 456 | `DMP_YACCB_PREL` | 458 |
| `DMP_ZACCB_PRE` | 460 | `DMP_ZACCB_PREL` | 462 | `DMP_TMP22` | 464 | `DMP_TAP_TIMER` | 466 |
| `DMP_TAP_THX` | 468 | `DMP_TAP_THY` | 472 | `DMP_TAP_THZ` | 476 | `DMP_TAPW_MIN` | 478 |
| `DMP_TMP25` | 480 | `DMP_TMP26` | 482 | `DMP_TMP27` | 484 | `DMP_TMP28` | 486 |
| `DMP_ORIENT` | 488 | `DMP_THRSH` | 490 | `DMP_ENDIANH` | 492 | `D_1_236` | 492 |
| `DMP_ENDIANL` | 494 | `DMP_BLPFNMTCH` | 496 | `DMP_BLPFNMTCL` | 498 | `DMP_BLPFNMXH` | 500 |
| `D_1_244` | 500 | `DMP_BLPFNMXL` | 502 | `DMP_BLPFNMYH` | 504 | `DMP_BLPFNMYL` | 506 |
| `DMP_BLPFNMZH` | 508 | `DMP_BLPFNMZL` | 510 | `D_2_12` | 524 | `D_0_22` | 534 |
| `D_0_24` | 536 | `CPASS_BIAS_X` | 564 | `CPASS_BIAS_Y` | 568 | `CPASS_BIAS_Z` | 572 |
| `CPASS_MTX_00` | 576 | `CPASS_MTX_01` | 580 | `CPASS_MTX_02` | 584 | `CPASS_MTX_10` | 588 |
| `CPASS_MTX_11` | 592 | `CPASS_MTX_12` | 596 | `CPASS_MTX_20` | 600 | `CPASS_MTX_21` | 604 |
| `D_2_96` | 608 | `D_2_108` | 620 | `D_ACT0` | 640 | `D_ACSX` | 644 |
| `D_ACSY` | 648 | `D_ACSZ` | 652 | `CPASS_MTX_22` | 700 | `D_2_244` | 756 |
| `D_2_248` | 760 | `D_2_252` | 764 | `FCFG_MAG_VAL` | 774 | `FCFG_MAG_MOV` | 791 |
| `FCFG_ACCEL_INIT` | 847 | `FCFG_4` | 880 | `FCFG_1` | 891 | `FCFG_2` | 895 |
| `FCFG_7` | 902 | `FCFG_3` | 936 | `FCFG_6` | 954 | `CFG_7` | 1014 |
| `CFG_MOTION_BIAS` | 1023 | `FCFG_5` | 1030 | `CFG_ACCEL_FILTER` | 1076 | `TEMPLABEL` | 1491 |
| `CFG_3` | 1623 | `CFG_3B` | 1625 | `CFG_3C` | 1627 | `CFG_3D` | 1629 |
| `CFG_4` | 1634 | `CFG_TAP_JERK` | 1722 | `CFG_20` | 1728 | `CFG_TAP_QUANTIZE` | 1730 |
| `CFG_TAP_SAVE_ACCB` | 1770 | `CFG_24` | 1782 | `CFG_25` | 1786 | `CFG_26` | 1790 |
| `CFG_ORIENT_1` | 1796 | `CFG_ORIENT_IRQ_1` | 1798 | `CFG_ORIENT_2` | 1816 | `CFG_ORIENT_IRQ_2` | 1821 |
| `CFG_ORIENT_IRQ_3` | 1826 | `CFG_5` | 1831 | `CFG_8` | 1854 | `CFG_GYRO_SOURCE` | 1859 |
| `CFG_9` | 1860 | `CFG_1` | 1865 | `CFG_14` | 1871 | `CFG_15` | 1876 |
| `CFG_EXTERNAL` | 1884 | `CFG_12` | 1894 | `CFG_21` | 1899 | `CFG_TAP0` | 1899 |
| `CFG_TAP1` | 1901 | `CFG_TAP2` | 1902 | `CFG_TAP3` | 1903 | `CFG_TAP4` | 1905 |
| `CFG_TAP5` | 1906 | `CFG_TAP6` | 1907 | `CFG_TAP7` | 1908 | `CFG_23` | 1911 |
| `CFG_16` | 1912 | `CFG_TAP_CLEAR_STICKY` | 1914 | `CFG_6` | 1920 | | |

### Image 2639

| name | addr | name | addr | name | addr | name | addr |
|---|---|---|---|---|---|---|---|
| `DMP_XGYR` | 2 | `DMP_YGYR` | 4 | `DMP_ZGYR` | 6 | `DMP_XACC` | 8 |
| `DMP_YACC` | 10 | `DMP_ZACC` | 12 | `DMP_ADC1` | 14 | `DMP_ADC2` | 16 |
| `DMP_ADC3` | 18 | `DMP_BIASUNC` | 20 | `DMP_FIFORT` | 22 | `DMP_INVGSFH` | 24 |
| `DMP_INVGSFL` | 26 | `DMP_1H` | 28 | `DMP_1L` | 30 | `DMP_BLPFSTCH` | 32 |
| `DMP_BLPFSTCL` | 34 | `DMP_BLPFSXH` | 36 | `D_0_36` | 36 | `DMP_BLPFSXL` | 38 |
| `DMP_BLPFSYH` | 40 | `DMP_BLPFSYL` | 42 | `DMP_BLPFSZH` | 44 | `DMP_BLPFSZL` | 46 |
| `DMP_BLPFMTC` | 48 | `DMP_SMC` | 50 | `DMP_BLPFMXH` | 52 | `D_0_52` | 52 |
| `DMP_BLPFMXL` | 54 | `DMP_BLPFMYH` | 56 | `DMP_BLPFMYL` | 58 | `DMP_BLPFMZH` | 60 |
| `DMP_BLPFMZL` | 62 | `DMP_BLPFC` | 64 | `DMP_SMCTH` | 66 | `D_SO_DATA` | 66 |
| `DMP_TAP_DIRECTION` | 68 | `DMP_TAP_COUNT` | 70 | `DMP_TAP_GATE` | 72 | `DMP_TAP_MIN_TAPS` | 74 |
| `DMP_BERR2NH` | 76 | `DMP_SMCINC` | 78 | `DMP_TAP_SHAKE_REJECT` | 80 | `DMP_ANGVBXL` | 82 |
| `DMP_TAP_SHAKE_COUNT_MAX` | 84 | `DMP_TAP_SHAKE_TIMEOUT_MAX` | 86 | `DMP_TAP_THZ` | 88 | `DMP_TAPW_MIN` | 90 |
| `DMP_TAP_PREV_JERK_Z` | 92 | `DMP_TAP_NEXT_TAP_THRES` | 94 | `DMP_ATCH` | 96 | `D_0_96` | 96 |
| `DMP_BIASUNCSF` | 98 | `DMP_ACT2H` | 100 | `DMP_ACT2L` | 102 | `DMP_GSFH` | 104 |
| `D_0_104` | 104 | `DMP_GSFL` | 106 | `DMP_GH` | 108 | `D_0_108` | 108 |
| `DMP_GL` | 110 | `DMP_0_5H` | 112 | `DMP_0_5L` | 114 | `DMP_0_0H` | 116 |
| `DMP_0_0L` | 118 | `DMP_1_0H` | 120 | `DMP_1_0L` | 122 | `DMP_1_5H` | 124 |
| `DMP_1_5L` | 126 | `DMP_TMP1AH` | 128 | `DMP_TMP1AL` | 130 | `DMP_TMP2AH` | 132 |
| `DMP_TMP2AL` | 134 | `DMP_TMP3AH` | 136 | `DMP_TMP3AL` | 138 | `DMP_TMP4AH` | 140 |
| `DMP_TMP4AL` | 142 | `DMP_XACCW` | 144 | `DMP_TMP5` | 146 | `DMP_XACCB` | 148 |
| `DMP_TMP8` | 150 | `DMP_YACCB` | 152 | `DMP_TMP9` | 154 | `DMP_ZACCB` | 156 |
| `DMP_TMP10` | 158 | `DMP_DZH` | 160 | `DMP_DZL` | 162 | `D_0_163` | 163 |
| `DMP_XGCH` | 164 | `DMP_XGCL` | 166 | `DMP_YGCH` | 168 | `DMP_YGCL` | 170 |
| `DMP_ZGCH` | 172 | `DMP_ZGCL` | 174 | `DMP_YACCW` | 176 | `DMP_TMP7` | 178 |
| `DMP_AFB1H` | 180 | `DMP_AFB1L` | 182 | `DMP_AFB2H` | 184 | `DMP_AFB2L` | 186 |
| `DMP_MAGFBH` | 188 | `D_0_188` | 188 | `DMP_MAGFBL` | 190 | `DMP_QT1H` | 192 |
| `D_0_192` | 192 | `D_FS_Q0` | 192 | `DMP_QT1L` | 194 | `DMP_QT2H` | 196 |
| `D_FS_Q1` | 196 | `DMP_QT2L` | 198 | `DMP_QT3H` | 200 | `D_FS_Q2` | 200 |
| `DMP_QT3L` | 202 | `DMP_QT4H` | 204 | `D_FS_Q3` | 204 | `DMP_QT4L` | 206 |
| `DMP_CTRL1H` | 208 | `DMP_CTRL1L` | 210 | `DMP_CTRL2H` | 212 | `DMP_CTRL2L` | 214 |
| `DMP_CTRL3H` | 216 | `DMP_CTRL3L` | 218 | `DMP_CTRL4H` | 220 | `DMP_CTRL4L` | 222 |
| `DMP_CTRLS1` | 224 | `D_0_224` | 224 | `DMP_CTRLSF1` | 226 | `DMP_CTRLS2` | 228 |
| `D_0_228` | 228 | `DMP_CTRLSF2` | 230 | `DMP_CTRLS3` | 232 | `D_0_232` | 232 |
| `DMP_CTRLSFNLL` | 234 | `DMP_CTRLS4` | 236 | `D_0_236` | 236 | `DMP_CTRLSFNL2` | 238 |
| `DMP_CTRLSFNL` | 240 | `DMP_TMP30` | 242 | `DMP_CTRLSFJT` | 244 | `DMP_TMP31` | 246 |
| `DMP_TMP11` | 248 | `DMP_CTRLSF2_2` | 250 | `DMP_TMP12` | 252 | `DMP_CTRLSF1_2` | 254 |
| `DMP_PREVPTAT` | 256 | `DMP_ACCZB` | 258 | `D_1_2` | 258 | `D_1_4` | 260 |
| `DMP_ACCXB` | 264 | `D_1_8` | 264 | `DMP_ACCYB` | 266 | `D_1_10` | 266 |
| `D_1_152` | 268 | `DMP_1HB` | 272 | `DMP_1LB` | 274 | `DMP_0H` | 276 |
| `DMP_0L` | 278 | `DMP_ASR22H` | 280 | `D_1_24` | 280 | `DMP_ASR22L` | 282 |
| `DMP_ASR6H` | 284 | `D_1_28` | 284 | `DMP_ASR6L` | 286 | `DMP_TMP13` | 288 |
| `D_SMD_ENABLE` | 288 | `DMP_TMP14` | 290 | `DMP_FINTXH` | 292 | `D_1_36` | 292 |
| `DMP_FINTXL` | 294 | `DMP_FINTYH` | 296 | `D_1_40` | 296 | `DMP_FINTYL` | 298 |
| `DMP_FINTZH` | 300 | `D_1_44` | 300 | `DMP_FINTZL` | 302 | `DMP_TMP1BH` | 304 |
| `DMP_TMP1BL` | 306 | `DMP_TMP2BH` | 308 | `DMP_TMP2BL` | 310 | `DMP_TMP3BH` | 312 |
| `DMP_TMP3BL` | 314 | `DMP_TMP4BH` | 316 | `DMP_TMP4BL` | 318 | `DMP_STXG` | 320 |
| `D_SMD_MOT_THLD` | 320 | `DMP_ZCTXG` | 322 | `DMP_STYG` | 324 | `DMP_ZCTYG` | 326 |
| `DMP_STZG` | 328 | `D_1_72` | 328 | `DMP_ZCTZG` | 330 | `D_1_74` | 330 |
| `DMP_CTRLSFJT2` | 332 | `DMP_CTRLSFJTCNT` | 334 | `D_1_79` | 335 | `DMP_PVXG` | 336 |
| `D_SMD_DELAY_CNTR` | 336 | `DMP_TMP15` | 338 | `DMP_PVYG` | 340 | `D_SMD_DELAY_THLD` | 340 |
| `DMP_TMP16` | 342 | `DMP_PVZG` | 344 | `D_1_88` | 344 | `DMP_TMP17` | 346 |
| `D_1_90` | 346 | `D_1_92` | 348 | `D_SMD_DELAY2_THLD` | 348 | `DMP_MNMFLAGH` | 352 |
| `D_1_96` | 352 | `D_SMD_EXE_STATE` | 352 | `DMP_MNMFLAGL` | 354 | `D_1_98` | 354 |
| `D_P_INIT` | 354 | `DMP_MNMTMH` | 356 | `DMP_MNMTML` | 358 | `DMP_MNMTMTHRH` | 360 |
| `DMP_MNMTMTHRL` | 362 | `D_1_106` | 362 | `D_P_HW_ID` | 362 | `DMP_MNMTHRH` | 364 |
| `D_1_108` | 364 | `DMP_MNMTHRL` | 366 | `DMP_ACCQD4H` | 368 | `D_1_112` | 368 |
| `DMP_ACCQD4L` | 370 | `DMP_ACCQD5H` | 372 | `DMP_ACCQD5L` | 374 | `DMP_ACCQD6H` | 376 |
| `DMP_ACCQD6L` | 378 | `DMP_ACCQD7H` | 380 | `DMP_ACCQD7L` | 382 | `DMP_ACCQD0H` | 384 |
| `D_DMP_RUN_CNTR` | 384 | `DMP_ACCQD0L` | 386 | `DMP_ACCQD1H` | 388 | `DMP_ACCQD1L` | 390 |
| `DMP_ACCQD2H` | 392 | `DMP_ACCQD2L` | 394 | `DMP_ACCQD3H` | 396 | `DMP_ACCQD3L` | 398 |
| `DMP_XN2H` | 400 | `D_1_128` | 400 | `DMP_XN2L` | 402 | `DMP_XN1H` | 404 |
| `DMP_XN1L` | 406 | `DMP_YN2H` | 408 | `DMP_YN2L` | 410 | `DMP_YN1H` | 412 |
| `DMP_YN1L` | 414 | `DMP_YH` | 416 | `D_1_160` | 416 | `DMP_YL` | 418 |
| `DMP_B0H` | 420 | `DMP_B0L` | 422 | `DMP_A1H` | 424 | `DMP_A1L` | 426 |
| `DMP_A2H` | 428 | `DMP_A2L` | 430 | `DMP_SEM1` | 432 | `D_1_176` | 432 |
| `D_9A_ACCURACY` | 432 | `DMP_FIFOCNT` | 434 | `D_1_178` | 434 | `D_CPASS_VALID` | 434 |
| `DMP_SH_TH_X` | 436 | `D_BM_BATCH_CNTR` | 436 | `DMP_PACKET` | 438 | `DMP_SH_TH_Y` | 440 |
| `D_BM_BATCH_THLD` | 440 | `DMP_FOOTER` | 442 | `DMP_SH_TH_Z` | 444 | `DMP_TEMP29` | 448 |
| `DMP_TEMP30` | 450 | `DMP_XACCB_PRE` | 452 | `D_BM_NUMWORD_TOFILL` | 452 | `DMP_XACCB_PREL` | 454 |
| `D_BM_ENABLE` | 454 | `DMP_YACCB_PRE` | 456 | `DMP_YACCB_PREL` | 458 | `DMP_ZACCB_PRE` | 460 |
| `DMP_ZACCB_PREL` | 462 | `DMP_TMP22` | 464 | `DMP_TAP_TIMER` | 466 | `DMP_TAP_THX` | 468 |
| `DMP_TAP_THY` | 472 | `D_1_218` | 474 | `DMP_TMP25` | 480 | `DMP_TMP26` | 482 |
| `CPASS_BIAS_X` | 484 | `DMP_TMP27` | 484 | `DMP_TMP28` | 486 | `CPASS_BIAS_Y` | 488 |
| `DMP_ORIENT` | 488 | `D_1_232` | 488 | `DMP_THRSH` | 490 | `CPASS_BIAS_Z` | 492 |
| `DMP_ENDIANH` | 492 | `D_1_236` | 492 | `DMP_ENDIANL` | 494 | `DMP_BLPFNMTCH` | 496 |
| `D_1_240` | 496 | `DMP_BLPFNMTCL` | 498 | `DMP_BLPFNMXH` | 500 | `D_1_244` | 500 |
| `DMP_BLPFNMXL` | 502 | `DMP_BLPFNMYH` | 504 | `DMP_BLPFNMYL` | 506 | `D_1_250` | 506 |
| `DMP_BLPFNMZH` | 508 | `D_1_252` | 508 | `DMP_BLPFNMZL` | 510 | `CPASS_MTX_00` | 516 |
| `CPASS_MTX_01` | 520 | `D_2_12` | 524 | `CPASS_MTX_10` | 528 | `CPASS_MTX_11` | 532 |
| `D_0_22` | 534 | `CPASS_MTX_12` | 536 | `D_0_24` | 536 | `CPASS_MTX_20` | 540 |
| `CPASS_MTX_21` | 548 | `CPASS_MTX_22` | 552 | `CPASS_MTX_02` | 588 | `D_2_96` | 608 |
| `D_2_108` | 620 | `D_ACT0` | 640 | `D_ACSX` | 644 | `D_ACSY` | 648 |
| `D_ACSZ` | 652 | `D_ACCEL_BIAS` | 660 | `D_2_208` | 720 | `D_ODR_CNTR_S0` | 720 |
| `D_ODR_CNTR_S2` | 722 | `D_ODR_CNTR_S1` | 724 | `FLICK_MSG` | 724 | `D_ODR_CNTR_S3` | 726 |
| `D_ODR_S0` | 728 | `FLICK_COUNTER` | 728 | `D_ODR_S2` | 730 | `D_ODR_S1` | 732 |
| `FLICK_LOWER` | 732 | `D_ODR_S3` | 734 | `D_2_224` | 736 | `D_ODR_CNTR_S4` | 736 |
| `D_ODR_CNTR_S6` | 738 | `D_ODR_CNTR_S5` | 740 | `D_ODR_CNTR_S7` | 742 | `D_ODR_S4` | 744 |
| `D_ODR_S6` | 746 | `D_2_236` | 748 | `D_ODR_S5` | 748 | `FLICK_UPPER` | 748 |
| `D_ODR_S7` | 750 | `D_2_244` | 756 | `D_2_248` | 760 | `D_2_252` | 764 |
| `D_PEDSTD_BP_B` | 796 | `D_PEDSTD_SB` | 808 | `D_PEDSTD_TIML` | 810 | `D_PEDSTD_SB_TIME` | 812 |
| `D_PEDSTD_TIMH` | 814 | `D_PEDSTD_BP_A4` | 832 | `D_PEDSTD_BP_A3` | 836 | `D_PEDSTD_BP_A2` | 840 |
| `D_PEDSTD_BP_A1` | 844 | `D_PEDSTD_STEPCTR` | 864 | `D_PEDSTD_PEAK` | 916 | `D_PEDSTD_PEAKTHRSH` | 920 |
| `D_PEDSTD_DECI` | 928 | `D_FS_LPQ0` | 944 | `D_FS_LPQ1` | 948 | `D_FS_LPQ2` | 952 |
| `D_FS_LPQ3` | 956 | `D_PEDSTD_TIMECTR` | 964 | `D_EXT_GYRO_BIAS_X` | 976 | `D_HOST_NO_MOT` | 976 |
| `D_EXT_GYRO_BIAS_Y` | 980 | `D_EXT_GYRO_BIAS_Z` | 984 | `D_AUTH_OUT` | 992 | `D_AUTH_IN` | 996 |
| `D_AUTH_A` | 1000 | `D_AUTH_B` | 1004 | `CFG_AUTH` | 1176 | `FCFG_1` | 1203 |
| `FCFG_2` | 1207 | `FCFG_7` | 1214 | `FCFG_3` | 1228 | `SMD_TP1` | 1369 |
| `SMD_TP2` | 1390 | `CFG_7` | 1425 | `CFG_MOTION_BIAS` | 1427 | `CFG_OUT_STEPDET` | 2030 |
| `CFG_OUT_3QUAT` | 2060 | `OUT_3QUAT_DAT` | 2070 | `CFG_OUT_QUAT` | 2095 | `OUT_QUAT_DAT` | 2105 |
| `CFG_OUT_PQUAT` | 2130 | `OUT_PQUAT_DAT` | 2139 | `CFG_OUT_ACCL` | 2164 | `OUT_ACCL_DAT` | 2173 |
| `CFG_OUT_GYRO` | 2198 | `OUT_GYRO_DAT` | 2207 | `CFG_OUT_CPASS` | 2232 | `OUT_CPASS_DAT` | 2241 |
| `CFG_OUT_PRESS` | 2266 | `OUT_PRESS_DAT` | 2275 | `CFG_FIFO_INT` | 2362 | `CFG_PED_ENABLE` | 2364 |
| `CFG_PED_INT` | 2593 | `CFG_PEDSTEP_DET` | 2605 | | | | |

## DINA mnemonic tables

| mnemonic | emd612 / hammerhead / mlsdk_mpu6050 | mlsdk_mpu3050 |
|---|---|---|
| `DINA00` | 0x00 | 0x00 |
| `DINA01` | 0x01 | 0x01 |
| `DINA04` | 0x04 | 0x04 |
| `DINA06` | 0x06 | 0x06 |
| `DINA08` | 0x08 | 0x08 |
| `DINA09` | 0x09 | 0x09 |
| `DINA0A` | 0x0a | 0x0a |
| `DINA0C` | 0x0c | 0x0c |
| `DINA0E` | 0x0e | 0x0e |
| `DINA10` | 0x10 | 0x10 |
| `DINA11` | 0x11 | 0x11 |
| `DINA14` | 0x14 | 0x14 |
| `DINA16` | 0x16 | 0x16 |
| `DINA18` | 0x18 | 0x18 |
| `DINA19` | 0x19 | 0x19 |
| `DINA1C` | 0x1c | 0x1c |
| `DINA1E` | 0x1e | 0x1e |
| `DINA20` | 0x20 | 0x20 |
| `DINA21` | 0x21 | 0x21 |
| `DINA22` | 0x22 | 0x22 |
| `DINA24` | 0x24 | 0x24 |
| `DINA25` | 0x25 | 0x25 |
| `DINA26` | 0x26 | 0x26 |
| `DINA28` | 0x28 | 0x28 |
| `DINA29` | 0x29 | 0x29 |
| `DINA2C` | 0x2c | 0x2c |
| `DINA2D` | 0x2d | 0x2d |
| `DINA2E` | 0x2e | 0x2e |
| `DINA30` | 0x30 | 0x30 |
| `DINA31` | 0x31 | 0x31 |
| `DINA34` | 0x34 | 0x34 |
| `DINA35` | 0x35 | 0x35 |
| `DINA36` | 0x36 | 0x36 |
| `DINA38` | 0x38 | 0x38 |
| `DINA39` | 0x39 | 0x39 |
| `DINA3C` | 0x3c | 0x3c |
| `DINA3D` | 0x3d | 0x3d |
| `DINA3E` | 0x3e | 0x3e |
| `DINA40` | 0x40 | 0x40 |
| `DINA41` | 0x41 | 0x41 |
| `DINA42` | 0x42 | 0x42 |
| `DINA44` | 0x44 | 0x44 |
| `DINA46` | 0x46 | 0x46 |
| `DINA48` | 0x48 | 0x48 |
| `DINA49` | 0x49 | 0x49 |
| `DINA4C` | 0x4c | 0x4c |
| `DINA4D` | 0x4d | 0x4d |
| `DINA4E` | 0x4e | 0x4e |
| `DINA50` | 0x50 | 0x50 |
| `DINA51` | 0x51 | 0x51 |
| `DINA54` | 0x54 | 0x54 |
| `DINA55` | 0x55 | 0x55 |
| `DINA56` | 0x56 | 0x56 |
| `DINA58` | 0x58 | 0x58 |
| `DINA59` | 0x59 | 0x59 |
| `DINA5A` | 0x5a | 0x5a |
| `DINA5C` | 0x5c | 0x5c |
| `DINA5D` | 0x5d | 0x5d |
| `DINA5E` | 0x5e | 0x5e |
| `DINA60` | 0x60 | 0x60 |
| `DINA61` | 0x61 | 0x61 |
| `DINA64` | 0x64 | 0x64 |
| `DINA66` | 0x66 | 0x66 |
| `DINA68` | 0x68 | 0x68 |
| `DINA69` | 0x69 | 0x69 |
| `DINA6C` | 0x6c | 0x6c |
| `DINA6D` | 0x6d | 0x6d |
| `DINA6E` | 0x6e | 0x6e |
| `DINA70` | 0x70 | 0x70 |
| `DINA71` | 0x71 | 0x71 |
| `DINA74` | 0x74 | 0x74 |
| `DINA75` | 0x75 | 0x75 |
| `DINA76` | 0x76 | 0x76 |
| `DINA78` | 0x78 | 0x78 |
| `DINA79` | 0x79 | 0x79 |
| `DINA7C` | 0x7c | 0x7c |
| `DINA7D` | 0x7d | 0x7d |
| `DINA7E` | 0x7e | 0x7e |
| `DINA80` | 0x80 | 0x80 |
| `DINA8B` | 0x8b | - |
| `DINA90` | 0x90 | 0x90 |
| `DINA91` | 0x91 | - |
| `DINAA0` | 0xa0 | 0xa0 |
| `DINAA3` | 0xa3 | - |
| `DINAAA` | 0xaa | - |
| `DINAAB` | 0xab | - |
| `DINAB1` | 0xb1 | - |
| `DINAB4` | 0xb4 | - |
| `DINAB6` | 0xb6 | - |
| `DINAB9` | 0xb9 | - |
| `DINAC0` | 0xb0 | 0xc0 **differs** |
| `DINAC1` | 0xb1 | 0xc1 **differs** |
| `DINAC2` | 0xb4 | 0xc2 **differs** |
| `DINAC3` | 0xb5 | 0xc3 **differs** |
| `DINAC4` | 0xb8 | 0xc4 **differs** |
| `DINAC5` | 0xb9 | 0xc5 **differs** |
| `DINAC8` | 0xc8 | 0xc8 |
| `DINAC9` | 0xc9 | 0xc9 |
| `DINACA` | 0xca | 0xca |
| `DINACB` | 0xcb | 0xcb |
| `DINACC` | 0xcc | 0xcc |
| `DINACD` | 0xcd | 0xcd |
| `DINACE` | 0xce | 0xce |
| `DINACF` | 0xcf | 0xcf |
| `DINAD8` | 0xd8 | 0xd8 |
| `DINADA` | 0xda | - |
| `DINADC` | 0xdc | - |
| `DINADD` | 0xdd | 0xdd |
| `DINADF` | 0xdf | - |
| `DINAF1` | 0xf1 | - |
| `DINAF2` | 0xf2 | - |
| `DINAF3` | 0xf3 | - |
| `DINAF8` | 0xf0 | 0xf8 **differs** |
| `DINAFE` | 0xfe | 0xfe |
| `DINBC0` | 0xc0 | - |
| `DINBC2` | 0xc2 | - |
| `DINBC4` | 0xc4 | - |
| `DINBC6` | 0xc6 | - |
| `DINBF8` | 0xf8 | - |
| `DINC00` | 0x00 | 0x00 |
| `DINC01` | 0x01 | 0x01 |
| `DINC02` | 0x02 | 0x02 |
| `DINC03` | 0x03 | 0x03 |
| `DINC08` | 0x08 | 0x08 |
| `DINC09` | 0x09 | 0x09 |
| `DINC0A` | 0x0a | 0x0a |
| `DINC0B` | 0x0b | 0x0b |
| `DINC10` | 0x10 | 0x10 |
| `DINC11` | 0x11 | 0x11 |
| `DINC12` | 0x12 | 0x12 |
| `DINC13` | 0x13 | 0x13 |
| `DINC18` | 0x18 | 0x18 |
| `DINC19` | 0x19 | 0x19 |
| `DINC1A` | 0x1a | 0x1a |
| `DINC1B` | 0x1b | 0x1b |
| `DINC20` | 0x20 | 0x20 |
| `DINC21` | 0x21 | 0x21 |
| `DINC22` | 0x22 | 0x22 |
| `DINC23` | 0x23 | 0x23 |
| `DINC28` | 0x28 | 0x28 |
| `DINC29` | 0x29 | 0x29 |
| `DINC2A` | 0x2a | 0x2a |
| `DINC2B` | 0x2b | 0x2b |
| `DINC30` | 0x30 | 0x30 |
| `DINC31` | 0x31 | 0x31 |
| `DINC32` | 0x32 | 0x32 |
| `DINC33` | 0x33 | 0x33 |
| `DINC38` | 0x38 | 0x38 |
| `DINC39` | 0x39 | 0x39 |
| `DINC3A` | 0x3a | 0x3a |
| `DINC3B` | 0x3b | 0x3b |
| `DINC40` | 0x40 | 0x40 |
| `DINC41` | 0x41 | 0x41 |
| `DINC42` | 0x42 | 0x42 |
| `DINC43` | 0x43 | 0x43 |
| `DINC48` | 0x48 | 0x48 |
| `DINC49` | 0x49 | 0x49 |
| `DINC4A` | 0x4a | 0x4a |
| `DINC4B` | 0x4b | 0x4b |
| `DINC50` | 0x50 | 0x50 |
| `DINC51` | 0x51 | 0x51 |
| `DINC52` | 0x52 | 0x52 |
| `DINC53` | 0x53 | 0x53 |
| `DINC58` | 0x58 | 0x58 |
| `DINC59` | 0x59 | 0x59 |
| `DINC5A` | 0x5a | 0x5a |
| `DINC5B` | 0x5b | 0x5b |
| `DINC60` | 0x60 | 0x60 |
| `DINC61` | 0x61 | 0x61 |
| `DINC62` | 0x62 | 0x62 |
| `DINC63` | 0x63 | 0x63 |
| `DINC68` | 0x68 | 0x68 |
| `DINC69` | 0x69 | 0x69 |
| `DINC6A` | 0x6a | 0x6a |
| `DINC6B` | 0x6b | 0x6b |
| `DINC70` | 0x70 | 0x70 |
| `DINC71` | 0x71 | 0x71 |
| `DINC72` | 0x72 | 0x72 |
| `DINC73` | 0x73 | 0x73 |
| `DINC78` | 0x78 | 0x78 |
| `DINC79` | 0x79 | 0x79 |
| `DINC7A` | 0x7a | 0x7a |
| `DINC7B` | 0x7b | 0x7b |
| `DIND40` | 0x40 | - |

Notes: `hammerhead` additionally defines `DIND40`=0x40 and the `DINADC/F2/AB/AA/F1/DF/DA/B1/B9/F3/8B/A3/91/B6/B4` set (as does `emd612`); the mlsdk header has none of those and instead switches the `DINA80..DINAC5`/`DINAF8`/`DINAFE` block on `CONFIG_MPU_SENSORS_MPU3050` vs `MPU6050A2/B1`. Mnemonic names are *not* the byte value where they differ across lineages: e.g. `DINAC0` is 0xc0 on 3050 but 0xb0 on 6050, while 0xc0 on 6050 is `DINBC0`; `DINAF8` is 0xf8 on 3050 but 0xf0 on 6050 (0xf8 = `DINBF8`).

