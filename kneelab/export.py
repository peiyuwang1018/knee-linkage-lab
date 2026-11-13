"""Machine-readable exports preserve configuration, signs and invalid rows."""
import csv
import io


def cycle_csv(result):
    stream=io.StringIO(newline="")
    columns=["t_s","q_deg","theta_deg","hip_height_m","com_accel_m_s2","load_factor",
             "foot_fz_n","tau_knee_nm","tau_input_nm","input_speed_rad_s","input_power_w",
             "rod_1_n","rod_2_n","rod_3_n","knee_rx_n","knee_rz_n","input_rx_n","input_rz_n",
             "elastic_twist_deg","closure_error_m","valid","reasons",
             "dead_center_clearance_deg","requested_start_deg","requested_end_deg",
             "preview_start_deg","preview_end_deg","requested_motion_complete"]
    columns += [f"rod_{i}_{end}_{axis}_n" for i in range(1,4) for end in ('A','B') for axis in ('x','z')]
    writer=csv.writer(stream);writer.writerow(columns)
    for r in result["rows"]:
        forces=(r["forces"] or [])+[None]*3
        kr=r["reaction_knee"] or [None,None];ir=r["reaction_input"] or [None,None]
        motion=result['motion']
        vectors=r['rod_end_forces'] or []
        vector_values=[vectors[i][end][axis] if i<len(vectors) else None
                       for i in range(3) for end in ('A','B') for axis in (0,1)]
        writer.writerow([r["t"],r["q_deg"],r["theta_deg"],r["hip_height_m"],r["com_accel"],r["load_factor"],
            r["fz"],r["tau_out"],r["tau_in"],r["motor_speed"],r["motor_power"],*forces[:3],*kr,*ir,
            r["twist_deg"],r["closure_m"],r["valid"],";".join(r["reasons"]),
            r['clearance_deg'],motion['requested_start_deg'],motion['requested_end_deg'],
            motion['start_deg'],motion['end_deg'],result['summary']['complete'],*vector_values])
    return stream.getvalue()


def scan_csv(result):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["rank","n","radius_mm","spacing_deg","center_mm","shank_mm","clocking_deg",
                     "peak_rod_n","peak_input_nm","peak_input_rad_s","peak_knee_reaction_n","pareto"])
    for i,r in enumerate(result["candidates"],1):
        c=r["config"]
        writer.writerow([i,c["n"],c["input_radius_mm"],c["spacing_deg"],c["center_mm"],c["shank_mm"],c["clocking_deg"],
                         r["peak_rod_n"],r["peak_input_nm"],r["peak_input_rad_s"],r["peak_knee_reaction_n"],r["pareto"]])
    return stream.getvalue()
