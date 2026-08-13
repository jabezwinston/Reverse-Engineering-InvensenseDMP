; Custom DMP telemetry - a register selection the stock firmware never emits.
; Site A (pre-accel block @1867): quaternion w and z only
        .lineage mantis
        selbank quat
        emit    quat_w, quat_z
