# DMP register map (bank selector x index)

Legend: `.` zero  `C` constant  `v` varying  `N` named  `?` no data

| bank | 00 | 08 | 10 | 18 | 20 | 28 | 30 | 38 | 40 | 48 | 50 | 58 | 60 | 68 | 70 | 78 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0x90` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x91` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x92` | C | v | v | C | C | v | C | C | C | v | v | C | C | v | v | C |
| `0x93` | v | v | C | C | v | C | C | C | v | C | C | C | v | C | C | C |
| `0x94` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x95` | v | v | v | C | v | v | v | . | v | v | v | C | v | v | v | C |
| `0x96` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x97` | C | C | C | C | C | . | C | C | C | C | C | C | C | C | C | C |
| `0x98` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x99` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x9a` | C | v | v | v | . | gyro_x | gyro_y | gyro_z | C | v | v | v | C | v | v | v |
| `0x9b` | v | v | v | C | v | v | v | . | v | v | v | C | v | v | v | C |
| `0x9c` | v | v | v | v | quat_w | quat_x | quat_y | quat_z | v | v | v | v | v | v | v | v |
| `0x9d` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x9e` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x9f` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |

## Position caveat

This table was measured from the probe site at 1868, which executes **before** the accel
computation. Accelerometer registers are therefore absent here; they live in bank `0x99`
indices `28`/`30`/`38` and are only visible from a post-accel probe (see RESULTS.md round 5).

## Identified (7)

- bank `0x9a` index `0x28` -> **gyro_x**
- bank `0x9a` index `0x30` -> **gyro_y**
- bank `0x9a` index `0x38` -> **gyro_z**
- bank `0x9c` index `0x20` -> **quat_w**
- bank `0x9c` index `0x28` -> **quat_x**
- bank `0x9c` index `0x30` -> **quat_y**
- bank `0x9c` index `0x38` -> **quat_z**

## Constants (124)

- bank `0x91` index `0x00` = `20650054`
- bank `0x91` index `0x08` = `1fef0000`
- bank `0x91` index `0x10` = `1a80000b`
- bank `0x91` index `0x18` = `32820001`
- bank `0x91` index `0x20` = `00650054`
- bank `0x91` index `0x28` = `ffef0000`
- bank `0x91` index `0x30` = `fa80000b`
- bank `0x91` index `0x38` = `12820001`
- bank `0x91` index `0x40` = `40650054`
- bank `0x91` index `0x48` = `3fef0000`
- bank `0x91` index `0x50` = `3a80000b`
- bank `0x91` index `0x58` = `52820001`
- bank `0x91` index `0x60` = `60650054`
- bank `0x91` index `0x68` = `5fef0000`
- bank `0x91` index `0x70` = `5a80000b`
- bank `0x91` index `0x78` = `72820001`
- bank `0x92` index `0x00` = `20020000`
- bank `0x92` index `0x18` = `20017fff`
- bank `0x92` index `0x20` = `00020000`
- bank `0x92` index `0x30` = `00017fff`
- bank `0x92` index `0x38` = `00017fff`
- bank `0x92` index `0x40` = `40020000`
- bank `0x92` index `0x58` = `40017fff`
- bank `0x92` index `0x60` = `60020000`
- bank `0x92` index `0x78` = `60017fff`
- bank `0x93` index `0x10` = `20017fff`
- bank `0x93` index `0x18` = `20017fff`
- bank `0x93` index `0x28` = `fffe8000`
- bank `0x93` index `0x30` = `00017fff`
- bank `0x93` index `0x38` = `00017fff`
- bank `0x93` index `0x48` = `3ffe8000`
- bank `0x93` index `0x50` = `40017fff`
- bank `0x93` index `0x58` = `40017fff`
- bank `0x93` index `0x68` = `5ffe8000`
- bank `0x93` index `0x70` = `5ffe8000`
- bank `0x93` index `0x78` = `60017fff`
- bank `0x94` index `0x00` = `200003e8`
- bank `0x94` index `0x08` = `20000001`
- bank `0x94` index `0x10` = `20017fff`
- bank `0x94` index `0x18` = `1ffe8001`
- bank `0x94` index `0x20` = `000003e8`
- bank `0x94` index `0x28` = `00000001`
- bank `0x94` index `0x30` = `00017fff`
- bank `0x94` index `0x38` = `fffe8001`
- bank `0x94` index `0x40` = `400003e8`
- bank `0x94` index `0x48` = `40000001`
- bank `0x94` index `0x50` = `40017fff`
- bank `0x94` index `0x58` = `3ffe8001`
- bank `0x94` index `0x60` = `600003e8`
- bank `0x94` index `0x68` = `60000001`
- bank `0x94` index `0x70` = `60017fff`
- bank `0x94` index `0x78` = `5ffe8001`
- bank `0x95` index `0x18` = `20000000`
- bank `0x95` index `0x58` = `40000000`
- bank `0x95` index `0x78` = `60000000`
- bank `0x96` index `0x00` = `20400000`
- bank `0x96` index `0x08` = `60000000`
- bank `0x96` index `0x10` = `22cb47a2`
- bank `0x96` index `0x18` = `40000000`
- bank `0x96` index `0x20` = `00400000`
- bank `0x96` index `0x28` = `40000000`
- bank `0x96` index `0x30` = `02cb47a2`
- bank `0x96` index `0x38` = `20000000`
- bank `0x96` index `0x40` = `40400000`
- bank `0x96` index `0x48` = `80000000`
- bank `0x96` index `0x50` = `42cb47a2`
- bank `0x96` index `0x58` = `60000000`
- bank `0x96` index `0x60` = `60400000`
- bank `0x96` index `0x68` = `a0000000`
- bank `0x96` index `0x70` = `62cb47a2`
- bank `0x96` index `0x78` = `80000000`
- bank `0x97` index `0x00` = `40000000`
- bank `0x97` index `0x08` = `20000000`
- bank `0x97` index `0x10` = `60000000`
- bank `0x97` index `0x18` = `80000000`
- bank `0x97` index `0x20` = `20000000`
- bank `0x97` index `0x30` = `40000000`
- bank `0x97` index `0x38` = `60000000`
- bank `0x97` index `0x40` = `60000000`
- bank `0x97` index `0x48` = `40000000`
- bank `0x97` index `0x50` = `80000000`
- bank `0x97` index `0x58` = `a0000000`
- bank `0x97` index `0x60` = `80000000`
- bank `0x97` index `0x68` = `60000000`
- bank `0x97` index `0x70` = `a0000000`
- bank `0x97` index `0x78` = `c0000000`
- bank `0x9a` index `0x00` = `20000000`
- bank `0x9a` index `0x40` = `40000000`
- bank `0x9a` index `0x60` = `60000000`
- bank `0x9b` index `0x18` = `20000000`
- bank `0x9b` index `0x58` = `40000000`
- bank `0x9b` index `0x78` = `60000000`
- bank `0x9e` index `0x00` = `5200139d`
- bank `0x9e` index `0x08` = `5200d0d6`
- bank `0x9e` index `0x10` = `52000800`
- bank `0x9e` index `0x18` = `600001f4`
- bank `0x9e` index `0x20` = `3200139d`
- bank `0x9e` index `0x28` = `3200d0d6`
- bank `0x9e` index `0x30` = `32000800`
- bank `0x9e` index `0x38` = `400001f4`
- bank `0x9e` index `0x40` = `7200139d`
- bank `0x9e` index `0x48` = `7200d0d6`
- bank `0x9e` index `0x50` = `72000800`
- bank `0x9e` index `0x58` = `800001f4`
- bank `0x9e` index `0x60` = `9200139d`
- bank `0x9e` index `0x68` = `9200d0d6`
- bank `0x9e` index `0x70` = `92000800`
- bank `0x9e` index `0x78` = `a00001f4`
- bank `0x9f` index `0x00` = `9f760000`
- bank `0x9f` index `0x08` = `60000000`
- bank `0x9f` index `0x10` = `2000d0d6`
- bank `0x9f` index `0x18` = `20002710`
- bank `0x9f` index `0x20` = `7f760000`
- bank `0x9f` index `0x28` = `40000000`
- bank `0x9f` index `0x30` = `0000d0d6`
- bank `0x9f` index `0x38` = `00002710`
- bank `0x9f` index `0x40` = `bf760000`
- bank `0x9f` index `0x48` = `80000000`
- bank `0x9f` index `0x50` = `4000d0d6`
- bank `0x9f` index `0x58` = `40002710`
- bank `0x9f` index `0x60` = `df760000`
- bank `0x9f` index `0x68` = `a0000000`
- bank `0x9f` index `0x70` = `6000d0d6`
- bank `0x9f` index `0x78` = `60002710`
