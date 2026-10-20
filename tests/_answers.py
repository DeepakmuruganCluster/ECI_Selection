"""Answers to the questions the interdependency audit added (owner 2026-10-17: "ask each one"), set to the values the tool
used silently before — so tests written before the audit keep testing what they tested."""
ASK = dict(estop=True, reset_pb=True, phase_lamps=True, lamp_va=1, wire_insulation="70", wire_circuits=1, cable_other=0,
           incomer_release="TM210", incomer_series="3VM", breaking_basis="icu", panel_signals=True, relay_make="finder", terminal_make="connectwell",
           io_conductor_mm2=1.5, smps_input="1P+N", plc_spare_pct=40, emc_filter="none", spd_config="3Ph+N+PE",
           spd_signalling=True, meter_comm="profinet", meter_supply="ac_dc", ss_thermistor=False,
           fuse_holder="switch_disconnector", contactor_suppressor="none", ss_comm="none", ss_hmi="none")


def ask(**kw) -> dict:
    """The audit answers, with the test's own values winning."""
    return {**ASK, **kw}


PER_CASE = {"coil_va": 10, "plc_cpu": "CPU 1513-1 PN", "plc_mc_mb": 24}


def answered(fn, _merge=True, **kw):
    """Run the requirement selection answering the audit's per-case questions the way the tool did silently before:
    the first company kit that fits, 10 VA coils, a soft-starter line contactor only for heavy duty (Class 20E)."""
    kw = ask(**kw) if _merge else dict(kw)
    for _ in range(5):
        r = fn(**kw)
        qs = (r.value or {}).get("questions") or []
        todo = [q for q in qs if q["input"].split(".", 1)[-1] in ("kit", "ss_line_contactor", *PER_CASE)]
        if not todo or r.status == "invalid":
            return r
        for q in todo:
            k, base = q["input"], q["input"].split(".", 1)[-1]
            if base == "kit":
                val = q["options"][0][0]
            elif base == "ss_line_contactor":
                val = any(m.get("starter") == "SS" and m.get("duty") == "heavy" for m in (r.value or {}).get("motors") or [])
            else:
                val = PER_CASE[base]
            if "." in k:
                n = int(k.split(".")[0][1:])
                ms = [dict(x) for x in (kw.get("motors") or [])]
                while len(ms) < n:
                    ms.append({})
                ms[n - 1][base] = val
                kw["motors"] = ms
            else:
                kw[k] = val
    return r


def auto(fn):
    """The requirement selection that answers the per-case audit questions (kit, coil VA, soft-starter line contactor,
    S7-1500 CPU / card) the old way — only when they are the only questions left, so tests of questions still see them."""
    def run(**kw):
        r = fn(**kw)
        for _ in range(5):
            qs = (r.value or {}).get("questions") or []
            if not qs or r.status == "invalid" or any(q["input"].split(".", 1)[-1] not in ("kit", "ss_line_contactor", *PER_CASE) for q in qs):
                return r
            r = answered(fn, _merge=False, **kw)
            return r
        return r
    run.__wrapped__ = getattr(fn, "__wrapped__", fn)
    return run


def complete(**kw) -> dict:
    """The inputs with the per-case audit questions answered the old way (for code that runs the selection itself:
    the Excel pack, alternatives, impact)."""
    from components.requirement.select import select
    had_conf = "confirmed" in kw
    kw = dict(kw)
    for _ in range(5):
        r = select(**{**kw, "confirmed": True})
        qs = (r.value or {}).get("questions") or []
        todo = [q for q in qs if q["input"].split(".", 1)[-1] in ("kit", "ss_line_contactor", *PER_CASE)]
        if not todo or r.status == "invalid":
            break
        for q in todo:
            k, base = q["input"], q["input"].split(".", 1)[-1]
            val = q["options"][0][0] if base == "kit" else PER_CASE.get(base, False) if base != "ss_line_contactor" else \
                any(m.get("starter") == "SS" and m.get("duty") == "heavy" for m in (r.value or {}).get("motors") or [])
            if "." in k:
                n = int(k.split(".")[0][1:])
                ms = [dict(x) for x in (kw.get("motors") or [])]
                while len(ms) < n:
                    ms.append({})
                ms[n - 1][base] = val
                kw["motors"] = ms
            else:
                kw[k] = val
    if not had_conf:
        kw.pop("confirmed", None)
    return kw


# the client-project options the tool chose silently before the audit (R-PRJ-20: now asked per panel)
OPTS = dict(cu_safety="sto", relays="latching", vfd_protection="fuse", cable_make="polycab", ct_make="rishabh",
            wire_insulation="70", terminals_per_channel=1, mc_copy_parameters=True, control_supply="transformer")


def with_opts(fn):
    def run(**kw):
        return fn(**{**OPTS, **kw})
    run.__wrapped__ = getattr(fn, "__wrapped__", fn)
    return run
