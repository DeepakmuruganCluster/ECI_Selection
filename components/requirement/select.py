"""Requirement: read a plain-language machine description, ask for what is missing, then run the selection.

Rules: rules.yaml (R-REQ-01 … 08). Strict reading: fixed patterns only, every fact shows the words it came
from, conflicting values are asked instead of picked, and nothing runs until the user confirms.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from components.aux_switchgear.select import select as aux_switchgear
from components.control_circuit.select import select as control_circuit
from components.control_power.select import select as control_power
from components.control_signalling.select import select as control_signalling
from components.internal_wiring.select import select as internal_wiring
from components.io_list.select import select as io_list
from components.plc.select import select as plc_select
from components.mccb.select import select as mccb
from components.mccb_3va.select import select as mccb_3va
from components.metering.select import select as metering
from components.panel.select import NOT_BUILT, coil_loads
from components.control_power.select import _coil as cp_coil, _method as cp_method
from components.power.select import protection_for, select as power_calc
from core import bom_edit
from core.makes import fill as fill_makes
from components.panel.select import select as panel_select
from core.provenance import load_yaml
from core.result import INFO, PASS, WARN, Result

HERE = Path(__file__).parent
COMPONENT = "requirement"
NUM = r"(?<![\d.,eE])(\d+(?:\.\d+|,\d{1,2}(?!\d))?|\.\d+)"
MAX_TEXT = 5000          # characters (R-REQ-01): a requirement is a paragraph; also bounds the reading time
PANEL_WORDS = ("panel", "inside", "internal", "cabinet", "enclosure")


class _Ask:
    """A reading that must be asked, not guessed (a range, two values in one phrase, zero, an ambiguous 1.500)."""
    def __repr__(self):
        return "ask"


ASK = _Ask()


MEDIA = ("water", "oil", "fluid", "liquid", "process", "winding", "bearing", "product", "medium", "steam", "gas", "coolant")
NEG = re.compile(r"\b(?:not|no|non|without|never)\b")


def _kw(m):
    """kW, asked when the number may be split or summed: 1 500 / 1'500 (thousands), 2 + 1 kW, 1.500, 0."""
    s, before = m.group(2), m.string[:m.start(2)]
    if re.fullmatch(r"\d{1,3}\.\d{3}", s) or re.search(r"\d[ '’\u2009\u202f]$", before) or re.search(r"\d\s*[+&]\s*$", before):
        return ASK
    return _pos(_f(s))


def _volt_pair(m):
    """U0/U notation only when U/U0 ≈ √3 (230/400, 240/415, 277/480, 400/690 …); otherwise two voltages → asked."""
    a, b = sorted((int(m.group(1)), int(m.group(2))))
    return float(b) if 1.70 <= b / a <= 1.76 else ASK


def _inst(value):
    """Cable installation words, unless negated shortly before ('not buried in ground') or answered 'no' after."""
    def conv(m):
        before = re.split(r"[,;\n]|\.(?=\s|$)", m.string[:m.start()])[-1][-25:].lower()
        after = m.string[m.end():m.end() + 8].lower()
        return None if NEG.search(before) or re.match(r"\s*\??\s*no\b", after) else value
    return conv


def _qty(n):
    return n if n > 0 else ASK


def _pos(x: float):
    """A length or power of 0 is not a value: ask."""
    return x if x > 0 else ASK


def _f(s: str) -> float:
    """A read number: decimal comma or point ('5,5' = 5.5, '.75' = 0.75)."""
    return float(s.replace(",", "."))


SITE_WORDS = ("site", "ambient", "outdoor", "outside", "indoor", "room", "air", "environment", "climate", "weather")


def _site_c(m):
    """°C is the site temperature only when its own phrase names the site / ambient (not the panel, water, a winding…)."""
    before = re.split(r"[,;\n]|\.(?=\s|$)", m.string[:m.start()])[-1].lower()
    after = re.split(r"[,;\n]|\.(?=\s|$)", m.string[m.end():])[0].lower()
    phrase = before + " " + after
    if any(w in phrase for w in PANEL_WORDS) or NEG.search(phrase) or any(re.search(rf"\b{w}\b", phrase) for w in MEDIA):
        return None
    return _f(m.group(1)) if any(re.search(rf"\b{w}\b", phrase) for w in SITE_WORDS) else None
FIELDBUS = {"profinet": "profinet", "ethernet/ip": "ethernet_ip", "profibus": "profibus", "modbus": "modbus"}
CURRENCY = {"€": "€", "eur": "€", "euro": "€", "euros": "€", "$": "$", "usd": "$", "dollars": "$", "₹": "₹",
            "inr": "₹", "rs": "₹", "rs.": "₹", "rupees": "₹", "£": "£", "gbp": "£"}

# what each input means, for facts and questions (plain language)
LABEL = {"kw": "Motor power (kW)", "qty": "Number of motors", "running": "Units running together (the rest standby)",
         "mpcb_range": "Client's MPCB setting range (A)", "starter": "Starter", "duty": "Drive duty",
         "voltage_v": "Supply voltage (V)", "frequency_hz": "Supply frequency (Hz)", "phases": "Supply phases",
         "fault_ka": "Fault level (kA)", "cable_m": "Motor cable length (m)", "flc_a": "Motor FLC (A)",
         "motor_pf": "Motor power factor", "panel_internal_c": "Temperature inside the panel (°C)",
         "cable_ambient_c": "Cable route temperature (°C)", "cu_encoder": "Motor encoder", "cu_safety": "Drive safety",
         "cu_fieldbus": "Fieldbus", "mc_copy_parameters": "Memory card (copy parameters)",
         "application": "Application", "ip_rating": "IP rating", "siting": "Installation", "country": "Country",
         "budget": "Budget", "site_ambient_c": "Site temperature (°C)", "hp": "Motor power (hp)",
         "meter": "Energy meter", "ct_make": "CT make (energy meter)", "plc_24v_a": "PLC / I/O modules / HMI 24 V current (A)",
         "plc_make": "PLC", "smps_brand": "24 V supply make",
         "spd": "Surge arrester at the incomer", "spd_make": "Surge arrester make", "meter_supply": "Energy meter supply", "pmr": "Phase monitoring relay",
         "control_supply": "Control supply", "kit": "Company kit",
         "meter_comm": "Energy meter communication", "wire_circuits": "Power circuits together in one duct",
         "cable_other": "Other cables beside each motor cable", "panel_signals": "Panel signals to the PLC",
         "estop": "Emergency stop on the door", "reset_pb": "Reset push button", "phase_lamps": "Phase lamps R / Y / B",
         "emc_filter": "Drive EMC filter", "plc_spare_pct": "PLC spare I/O (%)", "plc_cpu": "S7-1500 CPU",
         "plc_mc_mb": "S7-1500 memory card (MB)", "incomer_release": "Incomer trip unit", "incomer_series": "Incomer series", "fuse_holder": "Drive fuse holder", "contactor_suppressor": "Contactor surge suppressor", "ss_comm": "Soft starter communication",
         "ss_hmi": "Soft starter display", "ss_hmi_mounting": "Soft starter display mounting", "ss_hmi_cable_m": "Soft starter display cable (m)",
         "line_reactor_up_to_kw": "Line reactor on drives up to (kW)", "breaking_basis": "Incomer breaking capacity basis",
         "ss_line_contactor": "Soft starter line contactor", "ss_thermistor": "Soft starter thermistor input",
         "spd_signalling": "Surge arrester remote signal", "spd_config": "Surge arrester connection",
         "relay_make": "Interface relay make", "terminal_make": "Terminal make", "io_conductor_mm2": "I/O wire size (mm²)",
         "smps_input": "24 V supply input", "wire_insulation": "Internal wire insulation (°C)",
         "coil_va": "Contactor coil holding power (VA)", "lamp_va": "Pilot lamp power (VA)"}
QUESTION = {
    "kw": "What is the motor power in kW?",
    "qty": "How many of these motors are installed (duty and standby together)?",
    "starter": "How is the motor started: VFD, DOL or soft starter?",
    "voltage_v": "What is the supply voltage (V)? The country alone does not decide it here.",
    "fault_ka": "What is the fault level (kA) at the panel? Your utility or consultant gives it.",
    "panel_internal_c": "What temperature must the drives and starters work at, inside the panel (°C)?",
    "cable_ambient_c": "What is the air or ground temperature along the motor cable route (°C)?",
    "motor_pf": "What is the motor power factor when running (nameplate cos φ)?",
    "cable_m": "How long is the motor cable (m)?",
    "duty": "Drive duty: normal (pumps, fans) or heavy (conveyors, crushers)?",
    "cu_encoder": "Does the motor have an encoder for speed feedback?",
    "cu_safety": "Does the drive need safe torque off (STO)?",
    "cu_fieldbus": "Which fieldbus talks to the drive (PROFINET, EtherNet/IP, PROFIBUS, Modbus, none)?",
    "mc_copy_parameters": "Should each drive get a memory card to copy parameters?",
    "flc_a": "At 60 Hz the guide FLC table does not apply: what is the motor nameplate FLC (A)?",
    "ct_make": "Which make of current transformers for the energy meter: Rishabh or Selec?",
    "plc_make": "Which PLC family? (the tool picks the CPU and modules and works out their 24 V current)",
    "plc_24v_a": "How much 24 V DC current do the PLC, its I/O modules and the HMI draw in total (A)? (from their data sheets)",
    "spd": "Do you want a surge arrester at the incomer?",
    "spd_make": "Which make of surge arrester: Siemens, OBO or Phoenix?",
    "meter_supply": "How is the energy meter supplied: 230 V AC (wide-range supply) or 24 V DC?",
    "fuse_holder": "What holds each drive's three fuses?",
    "contactor_suppressor": "Surge suppressor (varistor) on each DOL contactor?",
    "ss_comm": "Soft starter communication module: PROFINET, PROFIBUS, EtherNet/IP, Modbus RTU / TCP, or none?",
    "ss_hmi": "Soft starter display (HMI module): Standard, High-Feature or none?",
    "ss_hmi_mounting": "Where is the soft starter's display mounted: on the panel door or in the device?",
    "ss_hmi_cable_m": "Display cable length to the door (0.5, 1, 2.5 or 5 m)?",
    "pmr": "Do you want a phase monitoring relay at the incomer?",
    "control_supply": "How is the 230 V control circuit fed: from a control transformer, or phase-neutral (no transformer)?",
    "kit": "Which company kit for this motor?",
    "meter_comm": "How does the energy meter talk: PROFINET (module), Modbus TCP (its own Ethernet) or not at all?",
    "wire_circuits": "How many power circuits run together in the busiest wiring duct (for the internal wire derating)?",
    "cable_other": "How many other cables run in the same tray beside each motor cable (0 = on its own)?",
    "panel_signals": "Do the panel's own signals go to the PLC (emergency stop, reset, phase failure, general trip and warning)?",
    "estop": "Is there an emergency stop push button on the panel door?",
    "reset_pb": "Is there a reset push button on the panel door?",
    "phase_lamps": "Are there phase indication lamps R / Y / B on the panel door?",
    "emc_filter": "Do the drives need a built-in EMC filter (class C2) or none?",
    "plc_spare_pct": "How much spare PLC I/O (%)?",
    "plc_cpu": "Which S7-1500 CPU?",
    "plc_mc_mb": "Which S7-1500 memory card size (MB)?",
    "incomer_release": "Which incomer trip unit: TM210 (fixed) or TM220 (adjustable)?",
    "incomer_series": "Which incomer breaker series: Siemens 3VA1 (TM240, adjustable thermal and magnetic) or 3VM (TM210 / TM220)?",
    "breaking_basis": "Must the incomer break the fault level on its ultimate (Icu) or service (Ics) breaking capacity?",
    "ss_line_contactor": "Does each soft starter get a line contactor?",
    "ss_thermistor": "Do the soft starters need a motor thermistor input?",
    "spd_signalling": "Does the surge arrester need a remote signalling contact?",
    "spd_config": "How is the surge arrester connected: 3 phases + N + PE, or 3 phases + PE?",
    "relay_make": "Which make of interface relays?",
    "terminal_make": "Which make of terminals?",
    "io_conductor_mm2": "Which wire size for the I/O wiring (mm²)?",
    "smps_input": "Is the 24 V supply fed single-phase (1P+N) or three-phase (3P)?",
    "wire_insulation": "Which internal wire insulation temperature: 70 °C (PVC) or 90 °C?",
    "coil_va": "What is the holding power (VA) of each contactor coil? (company kits and soft starter line contactors: not in the held data)",
    "lamp_va": "What is the power (VA) of each pilot lamp? (from the lamp data sheet)",
    "ss_protection": "The soft starter's breaker is not tested up to this fault level: protect it with gG fuses (type 1, 65 kA), "
                     "semiconductor fuses (type 2, 65 kA) or keep the breaker (only up to its printed kA)?",
}
# smallest internal power wire the designer can choose (decision RQ-9): none = ampacity only (the table's smallest, 0.5 mm²)
WIRE_FLOORS = (0.5, 0.75, 1.0, 1.5, 2.5)
ASKED_NOW = {"relay_make", "terminal_make", "io_conductor_mm2", "smps_input", "spd_config", "wire_insulation", "control_supply",
             "min_power_wire_mm2"}     # audit 2026-10-17: asked (or a designer setting), so never listed as a silent default
MOTOR_KEYS = ("kw", "qty", "starter", "duty", "application", "cable_m", "flc_a", "hp")
WORD_QTY = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
            "eighteen": 18, "nineteen": 19, "twenty": 20}
KW = r"(?:(?<![\d.,])\d+\s*[x×*]\s*)?(?<![\d.,eE])(?:\d+(?:\.\d+|,\d{1,2}(?!\d))?|\.\d+)\s*kW\b"
# R-REQ-09: clause ends; 'and', 'plus' and commas split only when a new kW follows
SPLIT = (r";|\n|\.(?=\s|$)|(?:,\s+|,(?=\D)|\s+and\s+|\s+plus\s+)(?=(?:an?\s+|(?:" + "|".join(WORD_QTY) + r")\s+)?"
         r"(?:[A-Za-z][\w/-]*\s+){0,3}"
         + KW + ")")


@lru_cache(maxsize=None)
def _rules() -> dict:
    return load_yaml(HERE / "rules.yaml")


def _patterns() -> list[tuple[str, str, object]]:
    """(fact, regex, how to turn the match into a value)."""
    p = _rules()["params"]
    apps = "|".join(p["heavy_words"] + p["normal_words"])
    countries = "|".join(re.escape(c) for c in sorted(p["countries"], key=len, reverse=True))
    return [
        ("kw", rf"(?:(?<![\d.,])(\d+)\s*[x×*]\s*)?{NUM}\s*kW\b",
         _kw),
        ("qty", rf"(?<![\d.,])(\d+)\s*[x×*]\s*{NUM}\s*kW\b", lambda m: _qty(int(m.group(1)))),
        ("qty", rf"{NUM}\s*kW\b[^;,.\d]{{0,30}}?\s[x×*]\s*(\d+)\b", lambda m: _qty(int(m.group(2)))),
        ("qty", r"\b(\d+)\s*(?:nos\b|no\.|units\b|pcs\b|sets\b)", lambda m: _qty(int(m.group(1)))),
        ("qty", r"\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b", lambda m: _qty(int(m.group(1)))),
        # duty / standby notation (2+1, 2W+1S, 1 duty 1 standby): how many run is not a plain quantity → asked
        ("qty", r"(?<![\d.,])\d+\s*(?:W|working|duty)?\s*\+\s*\d+\s*(?:S|standby|stand-by)?\b(?!\s*kW)", lambda m: ASK),
        ("qty", r"\b\d+\s*(?:W|working|duty)\s*(?:\+|and|&)?\s*\d+\s*(?:S|standby|stand-by)\b", lambda m: ASK),
        ("qty", rf"\b({'|'.join(WORD_QTY)})\s+(?:x\s+)?{NUM}\s*kW\b",
         lambda m: WORD_QTY[m.group(1).lower()]),
        ("hp", rf"\b{NUM}\s*(?:hp|bhp)\b", lambda m: _f(m.group(1))),
        ("starter", r"\b(?:VFDs?|variable[- ](?:frequency|speed) drives?|frequency (?:converter|inverter)s?|inverters?"
                    r"|AC drives?)\b", lambda m: "VFD"),
        ("starter", r"\b(?:DOL|direct[- ]on[- ]line)\b", lambda m: "DOL"),
        ("starter", r"\bsoft[- ]?start(?:ers?|ing)?\b", lambda m: "SS"),
        ("starter", r"\b(?:star[- /]?delta|S/D|SDL|Y[- /]D|Y[- /]Δ|Y[- /]delta|wye[- /]delta)(?![\w])", lambda m: "SD"),
        ("duty", r"\b(heavy|normal)[- ]duty\b", lambda m: m.group(1).lower()),
        ("duty", r"\b(high|low) overload\b", lambda m: "heavy" if m.group(1).lower() == "high" else "normal"),
        # IEC 60038 'U0/U' notation (230/400 V or 400/230 V): the line voltage is the higher one
        ("voltage_v", r"\b(\d{3,4})\s*V?\s*/\s*(\d{3,4})\s*V(?:AC)?\b", _volt_pair),
        ("voltage_v", r"\b(\d{3,4})\s*V?\s*(?:-|–|to)\s*(\d{3,4})\s*V(?:AC)?\b", lambda m: ASK),
        ("voltage_v", r"(?<![/–-])(?<![/–-] )\b(\d{3,4})\s*V(?:AC)?\b(?!\s*(?:-|–|to|/)\s*\d)", lambda m: float(m.group(1))),
        ("frequency_hz", r"\b(50|60)\s*Hz\b", lambda m: float(m.group(1))),
        ("phases", r"\b(single|1)[- ]phase\b", lambda m: 1),
        ("phases", r"\b(three|3)[- ]phase\b", lambda m: 3),
        ("fault_ka", rf"\b{NUM}\s*kA\b", lambda m: _f(m.group(1))),
        ("cable_m", rf"\b{NUM}\s*m(?:etres?|eters?)?\s+(?:of\s+)?(?:motor\s+)?cables?\b", lambda m: _pos(_f(m.group(1)))),
        ("cable_m", rf"\bcable(?:\s+length)?\s*(?:of\s*|=\s*|:\s*)?{NUM}\s*m\b", lambda m: _pos(_f(m.group(1)))),
        ("cable_m", rf"\bcables?(?:\s+lengths?)?\s*(?:of\s*|=\s*|:\s*)?{NUM}\s*m\s*(?:and|or|/|,|to|-|–)\s*{NUM}\s*m\b",
         lambda m: ASK),
        ("cable_m", rf"\bcables?\b[^;\n]{{0,40}}?{NUM}\s*m\b[^;\n]{{0,40}}?\b(?:and|or|,)\b[^;\n]{{0,20}}?{NUM}\s*m\b",
         lambda m: ASK),
        ("flc_a", rf"\b(?:FLC|full[- ]load current)\s*(?:of\s*|=\s*|:\s*)?{NUM}\s*A\b", lambda m: _f(m.group(1))),
        ("motor_pf", r"\b(?:pf|power factor|cos\s*(?:φ|phi))\s*(?:of\s*|=\s*|:\s*)?(?<![\d.,])(\d*[.,]?\d+)(?![\d.,])",
         lambda m: _f(m.group(1))),
        ("motor_pf", r"\b(?:pf|power factor|cos\s*(?:φ|phi))\s*(?:of\s*|=\s*|:\s*)?\d*[.,]?\d+\s*(?:-|–|to|/)\s*\d*[.,]?\d+",
         lambda m: ASK),
        ("cu_safety", r"\b(?:STO|safe torque off)\b", lambda m: "sto"),
        ("cu_fieldbus", r"\b(PROFINET|EtherNet/IP|PROFIBUS|Modbus)\b", lambda m: FIELDBUS[m.group(1).lower()]),
        ("cu_encoder", r"\b(?:no|without)\s+encoder\b", lambda m: False),
        ("cu_encoder", r"\b(?<!no )(?<!without )encoders?\b", lambda m: True),
        ("application", rf"\b({apps})s?\b", lambda m: m.group(1).lower()),
        ("ip_rating", r"\bIP\s?(\d{2}[A-Z]?)\b", lambda m: "IP" + m.group(1)),
        ("siting", r"\b(outdoor|indoor)s?\b", lambda m: m.group(1).lower()),
        ("country", rf"\b({countries})\b", lambda m: m.group(1)),
        ("budget", r"(?:\b(under|below|less than|max(?:imum)?|within|up to)\s+)?(€|\$|£|₹|\bEUR\b|\bUSD\b|\bINR\b|\bGBP\b|\bRs\.?)"
                   r"\s?(?<![\d.,])(\d[\d,]*(?:\.\d+)?)", lambda m: (m.group(1), m.group(2), m.group(3))),
        ("budget", r"(?:\b(under|below|less than|max(?:imum)?|within|up to)\s+)?(?<![\d.,])(\d[\d,]*(?:\.\d+)?)\s*"
                   r"(EUR|euros?|USD|dollars|INR|rupees|GBP)\b", lambda m: (m.group(1), m.group(3), m.group(2))),
        ("meter", r"\b(?:energy meter|metering|power meter|kwh meter|multifunction meter)s?\b", lambda m: True),
        ("spd", r"\b(?:surge (?:arrester|arrestor|protection|protective device)s?|SPDs?|lightning protection)\b",
         lambda m: True),
        ("spd_make", r"\b(OBO(?: Bettermann)?|Phoenix Contact)\b",
         lambda m: "OBO" if m.group(1).upper().startswith("OBO") else "Phoenix"),
        ("pmr", r"\b(?:phase (?:monitoring|failure|sequence) relays?|PMR)\b", lambda m: True),
        ("site_ambient_c", r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:°\s*C|deg(?:rees?)?\s*C)\b", _site_c),
        ("panel_internal_c", r"\b(?:panel|inside|internal|cabinet|enclosure)\b[^,;.\n\d]{0,40}?(-?\d+(?:\.\d+)?)\s*(?:°\s*C|deg(?:rees?)?\s*C)\b",
         lambda m: float(m.group(1))),
        ("cable_installation", r"(?<!\bnon-)\b(?:buried|underground|in (?:the )?ground|direct(?:ly)? in (?:the )?ground)\b",
         _inst("ground")),
        ("cable_installation", r"\bin (?:a |the )?ducts?\b", _inst("duct")),
    ]


def _budget(v) -> str:
    limit, cur, amount = v
    sym = CURRENCY.get(cur.lower(), cur)
    return f"{'under ' if limit else ''}{sym}{amount}"


def _scan(text: str, offset: int, keys) -> dict[str, list]:
    found: dict[str, list] = {}
    for key, rx, conv in _patterns():
        if key not in keys:
            continue
        for m in re.finditer(rx, text, re.IGNORECASE):
            val = conv(m)
            if val is None:
                continue
            if key == "budget":
                val = _budget(val)
            found.setdefault(key, []).append({"value": val, "from": m.group(0).strip(),
                                              "start": offset + m.start() + (len(m.group(0)) - len(m.group(0).lstrip())),
                                              "end": offset + m.start() + len(m.group(0).rstrip())})
    return found


def _settle(found: dict[str, list]) -> tuple[dict, dict]:
    """One value per fact, or a conflict (R-REQ-02)."""
    facts, conflicts = {}, {}
    for key, hits in found.items():
        if len({str(h["value"]) for h in hits}) > 1 or any(h["value"] is ASK for h in hits):
            conflicts[key] = [h["from"] for h in hits]
        else:
            facts[key] = hits[0]
    return facts, conflicts


def read(text: str) -> tuple[dict, dict, list[dict]]:
    """→ (general facts, general conflicts, motors [{facts, conflicts, clause}]). R-REQ-01, 02, 09."""
    text = text.replace("\u2212", "-")      # typographic minus, same length (positions stay right)
    all_keys = {k for k, _, _ in _patterns()}
    general_keys = all_keys - set(MOTOR_KEYS)
    facts, conflicts = _settle(_scan(text, 0, general_keys))
    n_kw = len(re.findall(KW, text, re.IGNORECASE))
    if n_kw <= 1:
        f, c = _settle(_scan(text, 0, MOTOR_KEYS))
        return facts, conflicts, [{"facts": f, "conflicts": c, "clause": text}]
    motors, shared = [], {}
    pos = 0
    for m in [*re.finditer(SPLIT, text, re.IGNORECASE), None]:
        end = m.start() if m else len(text)
        clause = text[pos:end]
        found = _scan(clause, pos, MOTOR_KEYS)
        n = len(re.findall(KW, clause, re.IGNORECASE))
        if n == 1:
            f, c = _settle(found)
            motors.append({"facts": f, "conflicts": c, "clause": clause.strip()})
        elif n > 1:
            conflicts["kw"] = conflicts.get("kw", []) + [clause.strip() + " (two kW values in one part: separate them with ';')"]
        else:
            for k, hits in found.items():
                shared.setdefault(k, []).extend(hits)
        pos = m.end() if m else len(text)
    if not motors:   # every kW sat in a part with another kW (R-REQ-09): one motor, its kW asked
        motors.append({"facts": {}, "conflicts": {"kw": conflicts.pop("kw", [text.strip()])}, "clause": text.strip()})
    shared_facts, shared_conflicts = _settle(shared)
    for mo in motors:
        for k, f in shared_facts.items():
            if k not in mo["facts"] and k not in mo["conflicts"]:
                mo["facts"][k] = dict(f, shared=True)
        for k, words in shared_conflicts.items():
            if k not in mo["facts"]:
                mo["conflicts"][k] = words
    return facts, conflicts, motors


def _boolish(v):
    return v if isinstance(v, bool) or v is None else str(v).strip().lower() in ("1", "true", "yes", "on")


def select(text: str, kw: float | None = None, qty: int | None = None, starter: str | None = None,
           duty: str | None = None, voltage_v: float | None = None, fault_ka: float | None = None,
           panel_internal_c: float | None = None, cable_ambient_c: float | None = None,
           motor_pf: float | None = None, cable_m: float | None = None, flc_a: float | None = None,
           cu_encoder: bool | None = None, cu_safety: str | None = None, cu_fieldbus: str | None = None,
           mc_copy_parameters: bool | None = None, ct_make: str | None = None, plc_make: str | None = None,
           plc_24v_a: float | None = None, smps_brand: str | None = None, vfd_protection: str | None = None,
           io_edits: list | None = None, template: str | None = None, ss_protection: str | None = None, incomer_factor: float | None = None, min_power_wire_mm2: float | None = None,
           cable_make: str | None = None, cable_installation: str | None = None, dol_source: str | None = None,
           kit_accessories: bool | None = None, coil_va: float | None = None, lamp_va: float | None = None,
           control_supply: str | None = None, edits: list | None = None, power_edits: list | None = None,
           spd: bool | None = None, spd_make: str | None = None, pmr: bool | None = None, motors: list | None = None,
           removed: bool | None = None, kit: str | None = None,
           meter_comm: str | None = None, wire_circuits: int | None = None, cable_other: int | None = None,
           panel_signals: bool | None = None, estop: bool | None = None, reset_pb: bool | None = None,
           phase_lamps: bool | None = None, emc_filter: str | None = None, plc_spare_pct: float | None = None,
           plc_cpu: str | None = None, plc_mc_mb: int | None = None, incomer_release: str | None = None,
           breaking_basis: str | None = None, ss_line_contactor: bool | None = None, ss_thermistor: bool | None = None,
           spd_signalling: bool | None = None, spd_config: str | None = None, relay_make: str | None = None,
           terminal_make: str | None = None, io_conductor_mm2: float | None = None, smps_input: str | None = None,
           wire_insulation: str | None = None, meter: bool | None = None, meter_supply: str | None = None,
           incomer_series: str | None = None, fuse_holder: str | None = None, line_reactor_up_to_kw: float | None = None,
           contactor_suppressor: str | None = None, ss_comm: str | None = None, ss_hmi: str | None = None,
           ss_hmi_mounting: str | None = None, ss_hmi_cable_m: float | None = None, smps_split: str | None = None,
           smps_cpu_min_a: float | None = None, smps_io_min_a: float | None = None, smps_min_a: float | None = None,
           plc_io_min: dict | None = None,
           confirmed: bool = False) -> Result:
    inputs = {k: v for k, v in locals().items() if v is not None}
    res = Result(COMPONENT, inputs)
    if not (text or "").strip():
        return res.invalid("describe the machine: nothing to read")
    prm = _rules()["params"]
    if len(text or "") > MAX_TEXT:
        return res.invalid(f"the requirement text is {len(text):,} characters; describe the machine in at most "
                           f"{MAX_TEXT:,} (a paragraph per panel)")
    facts, conflicts, mos = read(text)
    multi = len(mos) > 1
    if multi:
        res.add("R-REQ-09", "several motors, one per part of the text",
                "; ".join(f"M{i} '{m['clause']}'" for i, m in enumerate(mos, 1)), INFO)

    # answers (R-REQ-03): general ones, then per motor
    general = {k: v for k, v in dict(voltage_v=voltage_v, fault_ka=fault_ka, panel_internal_c=panel_internal_c,
                                     cable_ambient_c=cable_ambient_c, motor_pf=motor_pf, cu_encoder=cu_encoder,
                                     cu_safety=cu_safety, cu_fieldbus=cu_fieldbus,
                                     mc_copy_parameters=mc_copy_parameters, ct_make=ct_make, plc_make=plc_make,
                                     plc_24v_a=plc_24v_a, smps_brand=smps_brand, vfd_protection=vfd_protection,
                                     ss_protection=ss_protection, incomer_factor=incomer_factor, template=template,
                                     min_power_wire_mm2=min_power_wire_mm2,
                                     cable_make=cable_make, cable_installation=cable_installation, dol_source=dol_source,
                                     kit_accessories=kit_accessories, coil_va=coil_va, lamp_va=lamp_va,
                                     control_supply=control_supply,
                                     spd=spd, spd_make=spd_make, pmr=pmr,
                                     # audit 2026-10-17 (owner: "ask each one"): no silent panel defaults
                                     meter_comm=meter_comm, wire_circuits=wire_circuits, cable_other=cable_other,
                                     panel_signals=panel_signals, estop=estop, reset_pb=reset_pb, phase_lamps=phase_lamps,
                                     emc_filter=emc_filter, plc_spare_pct=plc_spare_pct, plc_cpu=plc_cpu, plc_mc_mb=plc_mc_mb,
                                     incomer_release=incomer_release, breaking_basis=breaking_basis,
                                     ss_line_contactor=ss_line_contactor, ss_thermistor=ss_thermistor,
                                     spd_signalling=spd_signalling, spd_config=spd_config, relay_make=relay_make,
                                     terminal_make=terminal_make, io_conductor_mm2=io_conductor_mm2, smps_input=smps_input,
                                     wire_insulation=str(wire_insulation) if wire_insulation is not None else None,
                                     meter=meter, meter_supply=meter_supply, incomer_series=incomer_series,
                                     fuse_holder=fuse_holder, line_reactor_up_to_kw=line_reactor_up_to_kw,
                                     contactor_suppressor=contactor_suppressor, ss_comm=ss_comm, ss_hmi=ss_hmi,
                                     ss_hmi_mounting=ss_hmi_mounting, ss_hmi_cable_m=ss_hmi_cable_m, smps_split=smps_split,
                                     smps_cpu_min_a=smps_cpu_min_a, smps_io_min_a=smps_io_min_a, smps_min_a=smps_min_a,
                                     plc_io_min=plc_io_min).items()
               if v is not None}
    per_all = {k: v for k, v in dict(kw=kw, qty=qty, starter=starter, duty=duty, cable_m=cable_m,
                                     flc_a=flc_a, removed=removed, kit=kit).items() if v is not None}
    per_motor = [dict(x or {}) for x in (motors or [])]
    for i, ans in enumerate([per_all, *per_motor]):
        for k in list(ans):
            if ans[k] in (None, ""):
                del ans[k]
        if "starter" in ans:
            ans["starter"] = str(ans["starter"]).upper()
            if ans["starter"] not in ("VFD", "DOL", "SS", "SD"):
                return res.invalid(f"starter must be VFD, DOL, SD (star-delta) or SS (got {ans['starter']})")
        if "duty" in ans and ans["duty"] not in ("normal", "heavy"):
            return res.invalid(f"duty must be normal or heavy (got {ans['duty']})")
        for k in ("kw", "cable_m", "flc_a"):
            if k in ans:
                ans[k] = float(ans[k])
        if "qty" in ans:
            ans["qty"] = int(ans["qty"])
            if ans["qty"] < 1:
                return res.invalid(f"the number of motors must be at least 1 (got {ans['qty']})")
        # RFQ import (owner 2026-10-18, R-REQ-33): a motor's own tag, its running units, the client's MPCB range
        if i and "tag" in ans and not re.fullmatch(r"[A-Za-z0-9_\-/.@]{1,40}", str(ans["tag"])):
            return res.invalid(f"a motor tag is letters, digits and _ - / . @, at most 40 characters (got {ans['tag']!r})")
        if "running" in ans:
            try:
                ans["running"] = int(ans["running"])
            except (TypeError, ValueError):
                return res.invalid(f"running units must be a whole number (got {ans['running']!r})")
            if ans["running"] < 1 or ("qty" in ans and ans["running"] > ans["qty"]):
                return res.invalid(f"running units must be from 1 to the number of motors (got {ans['running']})")
        if "mpcb_range" in ans and not re.fullmatch(r"(?:\d+(?:\.\d+)?-)?\d+(?:\.\d+)?", str(ans["mpcb_range"])):
            return res.invalid(f"mpcb_range must be 'low-high' in A (got {ans['mpcb_range']!r})")
    tags_ = [str(a["tag"]) for a in per_motor if a.get("tag")]
    if len(tags_) != len(set(tags_)):
        return res.invalid("each motor tag once: " + ", ".join(sorted({t for t in tags_ if tags_.count(t) > 1})))
    for k in ("cu_encoder", "mc_copy_parameters", "spd", "pmr", "kit_accessories", "panel_signals", "estop", "reset_pb", "meter",
              "phase_lamps", "ss_line_contactor", "ss_thermistor", "spd_signalling"):
        if k in general:
            general[k] = _boolish(general[k])
    for k, allowed in (("vfd_protection", ("fuse", "msp", "breaker")), ("ss_protection", ("mpcb", "fuse_gg", "fuse_semi")),
                       ("cable_make", ("polycab", "kei")),
                       ("cable_installation", ("air", "ground", "duct")), ("dol_source", ("siemens", "company")),
                       ("control_supply", ("transformer", "phase_neutral")),
                       ("meter_comm", ("profinet", "modbus_tcp", "none")), ("meter_supply", ("ac_dc", "dc_24_60")), ("emc_filter", ("none", "C2")),
                       ("plc_cpu", ("CPU 1511-1 PN", "CPU 1513-1 PN", "CPU 1515-2 PN")), ("incomer_release", ("TM210", "TM220")), ("incomer_series", ("3VM", "3VA")), ("fuse_holder", ("switch_disconnector",)), ("contactor_suppressor", ("varistor", "none")),
                       ("ss_comm", ("profinet", "profibus", "ethernet_ip", "modbus_rtu", "modbus_tcp", "none")),
                       ("ss_hmi", ("standard", "high_feature", "none")), ("ss_hmi_mounting", ("door", "device")),
                       ("smps_split", ("single", "cpu_io")),
                       ("breaking_basis", ("icu", "ics")), ("spd_config", ("3Ph+N+PE", "3Ph+PE")),
                       ("relay_make", ("finder", "phoenix", "connectwell")), ("terminal_make", ("connectwell", "phoenix")),
                       ("smps_input", ("1P+N", "3P")), ("wire_insulation", ("70", "90"))):
        if k in general and general[k] not in allowed:
            return res.invalid(f"{k} must be one of {', '.join(allowed)} (got {general[k]})")
    for k, lo, hi, intg in (("wire_circuits", 1, 50, True), ("cable_other", 0, 50, True), ("plc_spare_pct", 0, 100, False),
                            ("plc_mc_mb", 1, 32768, True), ("io_conductor_mm2", 0.5, 4, False),
                            ("line_reactor_up_to_kw", 0, 1000, False), ("ss_hmi_cable_m", 0.5, 5, False),
                            ("smps_cpu_min_a", 0.1, 100, False), ("smps_io_min_a", 0.1, 100, False), ("smps_min_a", 0.1, 100, False)):
        if k in general:
            try:
                x = float(general[k])
            except (TypeError, ValueError):
                return res.invalid(f"{k} must be a number (got {general[k]})")
            if not lo <= x <= hi or (intg and x != int(x)):
                return res.invalid(f"{k} must be {'a whole number ' if intg else ''}from {lo:g} to {hi:g} (got {general[k]})")
            general[k] = int(x) if intg else x
    if "plc_io_min" in general:                      # R-REQ-36: the client's final I/O count per type (spare included)
        m = general["plc_io_min"]
        if not isinstance(m, dict) or set(m) - {"di", "do", "ai", "ao"} or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v != int(v) for v in m.values()):
            return res.invalid(f"plc_io_min must be {{di, do, ai, ao: whole number ≥ 0}} (got {m})")
    PLCS = ("omron", "siemens_s7200smart", "siemens_s71200g2", "siemens_s71500", "other", "none")
    if "plc_make" in general and general["plc_make"] not in PLCS:
        return res.invalid(f"plc_make must be one of {', '.join(PLCS)} (got {plc_make})")
    if "template" in general:                      # R-REQ-29: a template of the company sheets
        from core import templates as T_
        try:
            T_.get(str(general["template"]))
        except ValueError as e:
            return res.invalid(str(e))
    if "incomer_factor" in general and not 1 <= float(general["incomer_factor"]) <= 3:
        return res.invalid(f"incomer_factor must be from 1 to 3 (got {general['incomer_factor']})")
    if "min_power_wire_mm2" in general and float(general["min_power_wire_mm2"]) not in WIRE_FLOORS:
        return res.invalid(f"min_power_wire_mm2 must be one of {', '.join(f'{x:g}' for x in WIRE_FLOORS)} (got {general['min_power_wire_mm2']})")
    if "ct_make" in general and general["ct_make"] not in ("rishabh", "selec"):
        return res.invalid(f"ct_make must be rishabh or selec (got {ct_make})")
    if general or per_all or any(per_motor):
        res.add("R-REQ-03", "answers typed in the form take precedence",
                ", ".join(sorted({*general, *per_all, *[f"M{i}.{k}" for i, a in enumerate(per_motor, 1) for k in a]})), INFO)

    # general facts
    known = {k: dict(f, how="read") for k, f in facts.items()}
    for k, v in general.items():
        known[k] = {"value": v, "from": "", "start": None, "end": None, "how": "answered"}
        conflicts.pop(k, None)
    for key, words in conflicts.items():
        res.add("R-REQ-02", f"one value for {LABEL.get(key, key).lower()}", "not read, asked: " + " / ".join(words), WARN)
    g = {k: f["value"] for k, f in known.items()}
    if "motor_pf" in g and not 0 < g["motor_pf"] <= 1:
        res.add("R-REQ-02", "power factor 0 < cos φ ≤ 1", f"{g['motor_pf']:g} read from '{known['motor_pf']['from']}' is "
                "impossible: not used (the cable takes the worst-case drop)", WARN)
        del g["motor_pf"], known["motor_pf"]
    # R-REQ-30 (owner 2026-10-16): a template is a finished order — nothing is asked; what its words do not give comes
    # from its own lines, else the template defaults, each shown as 'template' and editable
    if general.get("template"):
        from core import templates as T_
        for k, (val, why) in T_.defaults(general["template"], prm["template_defaults"]).items():
            if k not in g:
                g[k] = val
                known[k] = {"value": val, "from": why, "start": None, "end": None, "how": "template"}
            elif k == "control_supply" and g[k] != val:     # audit 2026-10-17: the designer's choice against the template's lines
                res.add("R-REQ-30", "the template's control supply follows its own lines",
                        f"control supply {g[k]} chosen, but the template's lines give {val} ({why}): the template BOM keeps its "
                        "lines — edit the BOM (remove the transformer, add the control MCB) to follow the choice", WARN)
        confirmed = True
    # R-REQ-20: worked out, not asked
    derived = []
    if ("cable_ambient_c" not in g and "cable_ambient_c" not in conflicts and "site_ambient_c" in g
            and "cable_installation" not in conflicts
            and (g.get("cable_installation") or prm["panel_defaults"]["cable_installation"]) == "air"):
        known["cable_ambient_c"] = dict(known["site_ambient_c"], how="derived")
        g["cable_ambient_c"] = g["site_ambient_c"]
        derived.append(f"cable route temperature = site temperature {g['site_ambient_c']:g} °C (cables in air)")
    if "motor_pf" not in g:
        derived.append("motor power factor not needed: each motor cable takes the worst-case voltage drop (R-CAB-09)")

    # motor facts
    motor_rows = []
    for i, mo in enumerate(mos, 1):
        mk = {k: dict(f, how="read") for k, f in mo["facts"].items() if k != "hp"}
        mconf = dict(mo["conflicts"])
        if "hp" in mo["facts"] and "kw" not in mo["facts"]:
            mconf["kw"] = [mo["facts"]["hp"]["from"] + " (hp is not used: give kW)"]
        app = mk.get("application")
        if app and "duty" not in mk and "duty" not in mconf:
            suggested = "heavy" if app["value"] in prm["heavy_words"] else "normal"
            mk["duty"] = {"value": suggested, "from": app["from"], "start": app["start"], "end": app["end"],
                          "how": "suggested"}
            res.add("R-REQ-05", "duty suggested by the application",
                    f"{'M%d: ' % i if multi else ''}{app['value']} → {suggested} (confirm)", INFO)
        ans = {**per_all, **(per_motor[i - 1] if i <= len(per_motor) else {})}
        own_tag = ans.pop("tag", None)                               # R-REQ-33: the client's tag (RFQ import)
        gone = _boolish(ans.pop("removed", False)) is True          # R-REQ-28: removed by the designer
        for k, v in ans.items():
            mk[k] = {"value": v, "from": "", "start": None, "end": None, "how": "answered"}
            mconf.pop(k, None)
        if "qty" not in mk and "qty" not in mconf:
            mk["qty"] = {"value": 1, "from": "", "start": None, "end": None, "how": "assumed"}
        for key, words in mconf.items():
            res.add("R-REQ-02", f"{'M%d: ' % i if multi else ''}one value for {LABEL.get(key, key).lower()}",
                    "not read, asked: " + " / ".join(words), WARN)
        motor_rows.append({"tag": str(own_tag) if own_tag else f"M{i}", "known": mk, "conflicts": mconf, "clause": mo.get("clause", ""), "removed": gone})
    res.add("R-REQ-01", "facts read from the text (each with its words)",
            "; ".join([f"{LABEL.get(k, k)} = {f['value']} ('{f['from']}')" for k, f in facts.items()]
                      + [f"{m['tag']} {LABEL.get(k, k)} = {f['value']} ('{f['from']}')" for m in motor_rows
                         for k, f in m["known"].items() if f["how"] == "read"]) or "none", PASS)

    if general.get("template"):                                      # R-REQ-30: the motor cable is a template default too
        for m in motor_rows:
            if "cable_m" not in m["known"] and "cable_m" not in m["conflicts"]:
                m["known"]["cable_m"] = {"value": float(prm["template_defaults"]["cable_m"]), "from": "template default",
                                         "start": None, "end": None, "how": "template"}
        from components.feeder_kit.select import kit_id as _kit_id, _kits as _all_kits
        t_ = T_.get(str(general["template"]))
        own = next((k for k in _all_kits() if k["ref"] == t_["ref"] and k["sheet"].strip() == t_["sheet"]
                    and (k.get("row") or 0) == (t_.get("row") or 0)), None)
        for m in motor_rows:                                         # the template is its own company kit (R-KIT-05)
            if own is not None and "kit" not in m["known"]:
                m["known"]["kit"] = {"value": _kit_id(own), "from": "the template itself", "start": None, "end": None, "how": "template"}
    # R-REQ-28: motors removed by the designer leave the design (the others keep their tags)
    gone_ = [m["tag"] for m in motor_rows if m["removed"]]
    if gone_:
        res.add("R-REQ-28", "motors removed by the designer", ", ".join(gone_), WARN, "designer edit")
    all_rows, motor_rows = motor_rows, [m for m in motor_rows if not m["removed"]]
    if not motor_rows:
        return res.invalid("every motor is removed: nothing to select (restore one)")
    # R-REQ-04: what the selection needs
    mv = [{**{k: f["value"] for k, f in m["known"].items()}, "tag": m["tag"]} for m in motor_rows]
    for v_ in mv:                                    # R-REQ-33: running units within the motor's quantity
        if v_.get("running") and v_.get("qty") and int(v_["running"]) > int(v_["qty"]):
            return res.invalid(f"{v_['tag']}: {v_['running']} running but only {v_['qty']} motor(s)")
    own = [v_ for v_ in mv if not re.fullmatch(r"M\d+", v_["tag"]) or v_.get("running") or v_.get("mpcb_range")]
    if own:
        res.add("R-REQ-33", "the client's tag, running units and MPCB range per motor (RFQ)",
                "; ".join(v_["tag"] + "".join(f", {LABEL[k].lower()} {v_[k]}" for k in ("running", "mpcb_range") if v_.get(k))
                          for v_ in own[:12]) + (f"; … {len(own) - 12} more" if len(own) > 12 else ""), INFO, "owner 2026-10-18")
    any_vfd = any(v.get("starter") == "VFD" for v in mv)
    need = ["voltage_v", "fault_ka", "panel_internal_c", "cable_ambient_c"]
    if any_vfd:
        need += ["cu_encoder", "cu_safety", "cu_fieldbus", "mc_copy_parameters"]
    if g.get("meter"):
        need.append("ct_make")
    need += ["plc_make", "spd", "pmr"]  # R-REQ-14
    need.append("control_supply")       # CC-1 (owner 2026-10-17): asked every time, no default
    # audit 2026-10-17 (owner: "ask each one"): what was a silent panel default is asked, each where it matters
    starters_ = {v.get("starter") for v in mv}
    if g.get("template"):                # R-REQ-30: a template is a finished order — its defaults answer these (shown 'template')
        starters_ = set()
    need += [] if g.get("template") else ["estop", "reset_pb", "phase_lamps", "lamp_va", "wire_insulation", "wire_circuits", "cable_other",
             "incomer_series", "breaking_basis"] + ([] if g.get("incomer_series") == "3VA" else ["incomer_release"])
    if g.get("plc_make") not in (None, "none") and not g.get("template"):
        need += ["panel_signals", "relay_make", "terminal_make", "io_conductor_mm2", "smps_input"]
        if g.get("plc_make") != "other":
            need.append("plc_spare_pct")
        if g.get("plc_make") == "siemens_s71500":
            need += ["plc_cpu", "plc_mc_mb"]
    if g.get("meter") and not g.get("template"):
        need += ["meter_comm", "meter_supply"]
    if g.get("spd") and not g.get("template"):
        need += ["spd_config", "spd_signalling"]
    if any_vfd and not g.get("template"):
        need.append("emc_filter")
        if (g.get("vfd_protection") or prm["panel_defaults"]["vfd_protection"]) == "fuse":
            need.append("fuse_holder")                # R-VFD-18 (owner 2026-10-20): what holds the drive fuses
    if "DOL" in starters_ and not g.get("template"):
        need.append("contactor_suppressor")           # R-DOL-15 (owner 2026-10-20): a surge suppressor on each DOL contactor
    if "SS" in starters_:
        need += ["ss_line_contactor", "ss_thermistor"]
        if not g.get("template"):                     # R-SS-15 (owner 2026-10-20): communication and display, asked
            need += ["ss_comm", "ss_hmi"]
            if g.get("ss_hmi") not in (None, "none"):
                need.append("ss_hmi_mounting")
                if g.get("ss_hmi_mounting") == "door":
                    need.append("ss_hmi_cable_m")
    if g.get("plc_make") == "other":
        need.append("plc_24v_a")
    if g.get("spd"):
        need.append("spd_make")
    questions = [{"input": k, "question": QUESTION[k],
                  "why": "the text gives two values: " + " / ".join(conflicts[k]) if k in conflicts else "not in the text"}
                 for k in need if k not in g]
    if "kw" in conflicts and not any("kw" in v for v in mv):
        questions.insert(0, {"input": "kw", "question": QUESTION["kw"], "why": " / ".join(conflicts["kw"])})
    for m, v in zip(motor_rows, mv):
        mneed = ["kw", "starter", "cable_m"] + (["qty"] if "qty" in m["conflicts"] else [])
        if v.get("starter") in ("VFD", "SS"):     # the duty decides the drive rating / the soft starter's class
            mneed.append("duty")
        if g.get("frequency_hz") == 60:
            mneed.append("flc_a")
        for k in mneed:
            if k in v:
                continue
            why = ("the text gives two values: " + " / ".join(m["conflicts"][k])) if k in m["conflicts"] else "not in the text"
            q = {"input": f"{m['tag']}.{k}" if multi else k,
                 "question": (f"{m['tag']} ({v.get('kw', '?')} kW): " if multi else "") + QUESTION[k], "why": why}
            # QA 2026-10-16 (L5): a bare 'n m' in this motor's words is offered, never read (it could be a pump head)
            bare = re.findall(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s?m\b(?!\s*(?:head|hd|wc|bar|³|3))", m.get("clause", "")) if k == "cable_m" else []
            if bare and why == "not in the text":
                q["why"] = f"the text has '{bare[0]} m' without the word 'cable' — is that the cable length?"
                q["suggest"] = [float(b.replace(",", ".")) for b in bare[:2]]
            questions.append(q)
    # R-REQ-18: help with every question (quick picks, range with its source, why, where to find it)
    help_ = prm.get("question_help") or {}
    for q in questions:
        h = help_.get(q["input"].split(".", 1)[-1])
        if h:
            q["help"] = h
        if q.get("suggest"):          # the length seen in the text first among the quick picks
            q["help"] = {**(h or {}), "picks": q["suggest"] + [p for p in (h or {}).get("picks", []) if p not in q["suggest"]]}
    if any(q.get("help") for q in questions):
        res.add("R-REQ-18", "help with the questions (quick picks, ranges with sources)",
                f"{sum(1 for q in questions if q.get('help'))} of {len(questions)} question(s)", INFO)
    res.add("R-REQ-04", "everything the selection needs is known",
            "to answer: " + ", ".join(q["input"] for q in questions) if questions else "yes",
            WARN if questions else PASS)

    # R-REQ-06: recorded, not used
    why_not = {"ip_rating": "enclosure out of scope (owner 2026-10-12)",
               "siting": "enclosure out of scope (owner 2026-10-12)",
               "budget": "no price source held (owner 2026-10-12): no total is given",
               "country": "supply data per country not held: the supply voltage must be stated",
               "site_ambient_c": ("used as the cable route temperature (R-REQ-20); " if known.get("cable_ambient_c", {}).get("how") == "derived"
                                  else "") + "the temperature inside the panel is asked separately",
               "frequency_hz": "the drives accept 50 and 60 Hz; at 60 Hz the nameplate FLC is asked"}
    recorded = [{"fact": LABEL[k], "value": f["value"], "from": f["from"], "use": why_not[k]}
                for k, f in facts.items() if k in why_not]
    recorded += [{"fact": f"{m['tag']} motor power (hp)" if multi else LABEL["hp"], "value": mo["facts"]["hp"]["value"],
                  "from": mo["facts"]["hp"]["from"], "use": "hp is not used: give the power in kW"}
                 for m, mo in zip(all_rows, mos) if "hp" in mo["facts"]]
    if recorded:
        res.add("R-REQ-06", "recorded but not used",
                "; ".join(f"{r['fact']} {r['value']}: {r['use']}" for r in recorded), INFO)

    if derived:
        res.add("R-REQ-20", "worked out instead of asked", "; ".join(derived), INFO)
    ready = not questions
    single = mv[0] if not multi else {}
    value = {k: (single.get(k) if k in MOTOR_KEYS else g.get(k))
             for k in ("kw", "starter", "duty", "voltage_v", "frequency_hz", "fault_ka", "cable_m", "flc_a", "motor_pf",
                       "panel_internal_c", "cable_ambient_c", "cu_encoder", "cu_safety", "cu_fieldbus",
                       "mc_copy_parameters", "ct_make", "plc_make", "plc_24v_a", "smps_brand", "spd", "spd_make", "pmr",
                       "vfd_protection", "cable_make", "cable_installation", "dol_source", "kit_accessories", "coil_va",
                       "lamp_va", "control_supply",
                       "application", "ip_rating", "siting", "country", "budget",
                       "site_ambient_c")}
    value["qty"] = int(single["qty"]) if not multi and single.get("qty") else None   # None: asked (R-REQ-02)
    fact_rows = [{"fact": LABEL.get(k, k), "input": k, "value": f["value"], "from": f["from"], "how": f["how"],
                  "start": f["start"], "end": f["end"]} for k, f in known.items()]
    for m, v in zip(motor_rows, mv):
        for k, f in m["known"].items():
            if k == "duty" and v.get("starter") == "DOL":
                continue  # duty only matters for a drive
            fact_rows.append({"fact": (f"{m['tag']} · " if multi else "") + LABEL.get(k, k),
                              "input": f"{m['tag']}.{k}" if multi else k, "value": f["value"], "from": f["from"],
                              "how": f["how"] + (" (for every motor)" if f.get("shared") else ""),
                              "start": f["start"], "end": f["end"]})
    value.update({"n_motors": len(mos), "n_questions": len(questions), "ready": ready, "selected": False,
                  "motors": [{"tag": m["tag"], **{k: v.get(k) for k in ("kw", "qty", "starter", "duty", "application",
                                                                         "cable_m", "flc_a")}}
                             for m, v in zip(motor_rows, mv)],
                  "removed_motors": [{"tag": m["tag"], **{k: f["value"] for k, f in m["known"].items() if k in ("kw", "qty", "starter")}}
                                     for m in all_rows if m["removed"]],
                  "facts": fact_rows, "questions": questions, "recorded": recorded})
    for k in ("power_module", "protection_device", "control_unit", "memory_card", "operator_panel", "soft_starter", "mpcb", "contactor",
              "incomer", "incomer_in_a", "incomer_ib_a", "ct", "smps", "spd_article", "pmr_article", "plc_cpu",
              "transformer_va"):
        value[k] = None
    res.value, res.basis = value, "requirement text"

    if g.get("template") and any(v.get("kw") is None for v in mv):
        return _template_only(res, value, g, edits)
    if not ready:
        return res
    if not confirmed:
        res.add("R-REQ-07", "facts confirmed by the user before selection", "waiting for confirmation", WARN)
        return res
    return _run(res, value, g, mv, prm, edits, power_edits, io_edits)


def _template_only(res: Result, value: dict, g: dict, edits: list | None) -> Result:
    """R-REQ-30: a template whose name gives no motor kW (PROWASH 100 = 100 TPH, VSI 250 …): its lines and cost are the
    result; power, I/O and the diagram wait for the motors the designer adds. Nothing is asked."""
    from core import templates as T_
    t_ = T_.get(g["template"])
    bom = T_.bom(g["template"])
    n_edits = 0
    if edits:
        recs = []
        for i, e in enumerate(edits, 1):
            if not isinstance(e, dict):
                return res.invalid(f"edit {i} is not an edit")
            chk = bom_edit.check(e)
            if not chk["ok"]:
                return res.invalid(f"edit {i}: {chk['notes']}")
            recs.append({**e, "id": e.get("id", i), "panel": "machine", "line": e.get("line") or {},
                         "make": e.get("make") or chk.get("make"), "check": chk, "proposed_by": e.get("proposed_by", "designer")})
        bom, _ = bom_edit.apply(bom, recs, "machine")
        for b in bom:
            b.setdefault("unit_price_inr", None)
        n_edits = len(recs)
    why = "the template's name gives no motor kW (it is a client order by capacity / model): add its motors to get power and I/O"
    sc = T_.scope(g["template"])                      # R-REQ-31: only what the template lists — here too
    priced = [b for b in bom if b.get("unit_price_inr") is not None and isinstance(b.get("qty"), (int, float))]
    # the template's motors as one feeder for the drawing: its feeder lines, the starter its name gives, kW not stated
    feeders = [{"tag": "M1", "kw": None, "starter": t_["starter"] or "", "qty": t_["motors"], "running": t_["motors"],
                "status": "template", "flc_a": None, "devices": "template lines", "cable": "", "wire_ib_a": None}]
    res.add("R-REQ-30", f"template {t_['title']} ({t_['ref']} sheet '{t_['sheet']}'): its {len(bom)} lines and cost are the result", why, WARN, t_["ref"])
    value.update({"selected": True, "ready": True, "questions": [], "n_questions": 0, "bom": bom, "n_edits": n_edits,
                  "template": {"id": t_["id"], "title": t_["title"], "ref": t_["ref"], "sheet": t_["sheet"], "family": t_["family"]},
                  "template_lines": sum(1 for b in bom if b.get("status") == "template"), "template_checks": [], "template_fails": 0,
                  "rule_bom": [], "feeders": feeders, "power": None, "power_error": why, "incomplete": [], "load_list": "",
                  "scope": sc, "scope_plc": int(sc["plc"]), "scope_smps": int(sc["smps"]), "scope_incomer": int(sc["incomer"]),
                  "scope_ct": int(sc["control_transformer"]), "n_bom_lines": len(bom), "n_priced": len(priced), "n_open": 1,
                  "indicative_inr": round(sum(b["unit_price_inr"] * b["qty"] for b in priced), 2),
                  "voltage_v": g.get("voltage_v"), "fault_ka": g.get("fault_ka"), "control_supply": g.get("control_supply") if sc["control_transformer"] else None,
                  "io_list": [], "io_inputs": [], "io_outputs": [], "io_bus": [], "io_safety_list": [], "io_trace": [],
                  "design_logic": [], "open_points": [{"tag": "panel", "component": "requirement", "rule": "R-REQ-30", "kind": "warning", "point": why}],
                  "not_selected": [], "not_selected_detail": [], "vfd_boms": [], "removed_motors": value.get("removed_motors", []),
                  **{k: 0 for k in ("io_di", "io_do", "io_ai", "io_ao", "io_pn", "io_safety", "qty_relays", "qty_io_terminals")}})
    return res


def _run(res: Result, value: dict, g: dict, mv: list[dict], prm: dict, edits: list | None = None,
         power_edits: list | None = None, io_edits: list | None = None) -> Result:
    """R-REQ-07 … 13: the confirmed facts through every built component."""
    phases = int(g.get("phases") or 3)
    # R-REQ-31: with a template only what it lists is selected (a new machine: everything)
    from core import templates as T_
    scope = T_.scope(g["template"]) if g.get("template") else dict(T_.FULL_SCOPE)
    if g.get("plc_make") == "none":                  # R-REQ-31: the designer says this panel has no PLC
        scope["plc"] = False
    missing_ = [k for k, n in (("plc", "PLC (and its I/O, relays, terminals)"), ("smps", "24 V supply"), ("incomer", "incomer"),
                               ("control_transformer", "control circuit / transformer")) if not scope[k]]
    if missing_:
        res.add("R-REQ-31", "only what the template lists is selected", "not in this panel: " + ", ".join(
            dict((("plc", "PLC, its I/O, relays and terminals"), ("smps", "24 V supply"), ("incomer", "incomer"),
                  ("control_transformer", "control transformer")))[k] for k in missing_), INFO, "template")
    lines = []
    for i, v in enumerate(mv, 1):
        line = f"{v.get('tag') or f'M{i}'} {v['kw']:g} {v['starter']} cable={v['cable_m']:g}"
        if int(v.get("qty") or 1) > 1:
            line += f" qty={int(v['qty'])}"
            if v.get("running") and int(v["running"]) < int(v["qty"]):      # R-REQ-33: the rest are standby
                line += f" standby={int(v['qty']) - int(v['running'])}"
        if v.get("mpcb_range") and v["starter"] in ("DOL", "VFD"):           # R-REQ-33 / R-DOL-14 / R-VFD-19: the client's MPCB
            line += f" mpcb={v['mpcb_range']}"
        if v.get("flc_a"):
            line += f" flc={v['flc_a']:g}"
        if phases == 1:
            line += f" ph=1 v={g['voltage_v']:g}"
        if v["starter"] in ("VFD", "SS") and v.get("duty"):   # drive rating / soft starter class (R-SS-06)
            line += f" duty={v['duty']}"
        if v.get("application"):
            line += f" app={v['application'].replace(' ', '_')}"
        if v.get("kit"):
            line += f" kit={v['kit']}"
        lines.append(line)
    load_list = "\n".join(lines)
    # R-REQ-08: panel defaults, unless an experienced designer changed them (R-REQ-15)
    d = {**prm["panel_defaults"], **{k: g[k] for k in ("vfd_protection", "cable_make", "cable_installation", "dol_source")
                                     if g.get(k)}}
    if g.get("kit_accessories") is not None:
        d["kit_accessories"] = g["kit_accessories"]
    sd = prm["signalling_defaults"]
    changed = [k for k in ("vfd_protection", "cable_make", "cable_installation", "dol_source", "kit_accessories")
               if g.get(k) is not None]
    if changed:
        res.add("R-REQ-15", "panel defaults changed by the designer", ", ".join(f"{k} = {g[k]}" for k in changed), INFO)
    pic = g["panel_internal_c"]
    p = panel_select(load_list=load_list, fault_ka=g["fault_ka"], panel_internal_c=pic, motor_pf=g.get("motor_pf"),
                     cable_ambient_c=g["cable_ambient_c"], voltage_v=g["voltage_v"], coil=d["coil"],
                     ie_class=d["ie_class"], cable_installation=d["cable_installation"], cable_make=d["cable_make"],
                     vfd_protection=d["vfd_protection"], cu_encoder=g.get("cu_encoder"), cu_safety=g.get("cu_safety"),
                     cu_fieldbus=g.get("cu_fieldbus"), mc_copy_parameters=g.get("mc_copy_parameters"),
                     dol_source=d["dol_source"], kit_accessories=bool(d["kit_accessories"]),
                     ss_protection=g.get("ss_protection"), other_cables=g.get("cable_other"), emc_filter=g.get("emc_filter"),
                     ss_line_contactor=g.get("ss_line_contactor"), ss_thermistor=g.get("ss_thermistor"),
                     fuse_holder=g.get("fuse_holder"), line_reactor_up_to_kw=g.get("line_reactor_up_to_kw"),
                     suppressor=g.get("contactor_suppressor"), ss_comm=g.get("ss_comm"), ss_hmi=g.get("ss_hmi"),
                     ss_hmi_mounting=g.get("ss_hmi_mounting"), ss_hmi_cable_m=g.get("ss_hmi_cable_m"))
    if p.status == "invalid":
        return res.invalid(f"panel assembly: {p.checks[-1].value}")
    # R-REQ-24: a soft starter whose breaker is not tested up to the fault level → ask for its protection (never chosen silently)
    ss_iq = [o for o in p.value["open_points"] if o.get("rule") == "R-SS-08" and o.get("kind") == "refused" and "choose fuses" in o["point"]]
    if ss_iq and not g.get("ss_protection"):
        q = {"input": "ss_protection", "question": QUESTION["ss_protection"],
             "why": "; ".join(f"{o['tag']}: {o['point'].split(': ', 1)[-1]}" for o in ss_iq)}
        h = (prm.get("question_help") or {}).get("ss_protection")
        if h:
            q["help"] = h
        value.update({"questions": [q], "n_questions": 1, "ready": False, "selected": False})
        res.add("R-REQ-24", "soft starter protection at this fault level", q["why"] + " → asked", WARN, "IC10 3RW52 pp.6/63–6/65")
        return res
    # audit 2026-10-17 (owner: ask): a contactor coil whose power is not in the held data (company kits, a soft starter's
    # line contactor) → the coil VA is asked, where it matters — only with a control circuit in this panel
    unheld = [f["tag"] for f in p.value["feeders"] if f["status"] == "selected" and (
        (f["starter"] in ("DOL", "SD") and not (f.get("coil") or {}).get("hold"))
        or (f["starter"] == "SS" and re.search(r"\+ 3R[TF]", str(f.get("devices") or ""))))]
    if unheld and g.get("coil_va") is None and scope["control_transformer"] and not g.get("template") and \
            not any(o.get("kind") == "choose" for o in p.value["open_points"]):
        q = {"input": "coil_va", "question": QUESTION["coil_va"], "why": "coil power not in the held data for " + ", ".join(unheld)}
        h = (prm.get("question_help") or {}).get("coil_va")
        if h:
            q["help"] = h
        value.update({"questions": [q], "n_questions": 1, "ready": False, "selected": False})
        res.add("R-REQ-32", "contactor coil VA where the coil power is not held", q["why"] + " → asked", WARN)
        return res
    # audit 2026-10-17 (owner: ask): several company kits fit a motor, or none is named after its application → asked
    kq = [o for o in p.value["open_points"] if o.get("kind") == "choose" and o.get("rule") == "R-KIT-06"]
    if kq and not g.get("template"):         # a template's own lines are its kit: its rule check is not asked (R-REQ-30)
        multi_ = len(mv) > 1
        qs = [{"input": f"{o['tag']}.kit" if multi_ else "kit", "question": (f"{o['tag']}: " if multi_ else "") + QUESTION["kit"],
               "why": o["point"], "options": [[c["id"], c["title"]] for c in o["choices"]],
               "help": {"why": "A company kit brings the starter parts, lamps and terminals of the company costing sheet.",
                        "where": "Company costing sheets (OWN-PROPEL-DOL / OWN-PROPEL-COST)."}} for o in kq]
        value.update({"questions": qs, "n_questions": len(qs), "ready": False, "selected": False})
        res.add("R-REQ-32", "one company kit per motor (R-KIT-06)", "; ".join(o["point"] for o in kq) + " → asked", WARN)
        return res
    pv = p.value
    opens, logic, bom = list(pv["open_points"]), list(pv["design_logic"]), []

    def log(tag, r):
        logic.extend({"tag": tag, "component": r.component, "verdict": c.verdict, "rule": c.rule,
                      "requirement": c.requirement, "value": c.value, "source": c.source} for c in r.checks)
        for c in r.checks:
            if c.verdict in ("warn", "fail"):
                opens.append({"tag": tag, "component": r.component, "rule": c.rule,
                              "kind": "warning" if c.verdict == "warn" else "refused",
                              "point": f"{c.requirement}: {c.value}"})

    def add(group, article, desc, qty, unit, used_by, source, price=None, make=None):
        bom.append({"group": group, "article": article or "", "description": desc, "qty": qty, "unit": unit,
                    "used_by": used_by, "source": source, "unit_price_inr": price, "make": make})

    for b in pv["bom"]:
        cable = "cable (metres)" in b["description"]          # motor cables only (not an HMI connecting cable, owner 2026-10-20)
        kitline = "company kit" in b["description"]
        add("Motor cables" if cable else "Feeder accessories" if kitline and not b["article"].startswith(("LC1E", "GZ1E", "GV", "LRE",
                                                                                                        "LAEN", "GZ1AN"))
            and "2ASDT" not in b["article"] else "Feeders", b["article"], b["description"], b["qty"], "m" if cable else "no",
            ", ".join(b["used_by"]), "company kit (feeder_kit)" if kitline else "panel assembly (1, 2, 4, 5, 6)",
            b.get("unit_price_inr"), make=b.get("make"))

    # I/O list (23)
    io = io_list(load_list=load_list, vfd_sto=g.get("cu_safety") == "sto",
                 vfd_control="hardwired" if g.get("cu_fieldbus") == "none" else "fieldbus",
                 panel_signals=bool(g.get("panel_signals")), pmr=bool(g.get("pmr")),     # R-IO-10: asked (audit 2026-10-17)
                 edits=io_edits)                                  # R-IO-12: the designer's I/O edits
    if io.status == "invalid":
        return res.invalid("I/O list: " + next(c.value for c in io.checks if c.verdict == "fail"))
    log("I/O list", io)
    iv = io.value
    if not scope["plc"]:                     # R-REQ-31: no PLC in this panel → no PLC inputs / outputs (nor relays, terminals)
        iv = {**iv, **{k: 0 for k in ("io_di", "io_do", "io_ai", "io_ao", "io_pn", "io_safety", "n_signals", "n_inputs", "n_outputs")},
              "io_list": [], "inputs": [], "outputs": [], "bus": [], "safety": []}

    # R-REQ-11: relays, terminals, internal wiring
    qty_relays = qty_terms = 0
    if iv["io_do"]:
        rel = control_signalling(dol_outputs=0, other_outputs=iv["io_do"], relay_make=g.get("relay_make", sd["relay_make"]),
                                 panel_internal_c=pic)
        log("relays", rel)
        for b in (rel.value or {}).get("bom", []):
            add("Control and signalling", b["article"], b["item"], b["qty"], "no", "PLC outputs", b["source"])
        qty_relays = sum(b["qty"] for b in (rel.value or {}).get("bom", []) if "relay" in b["item"].lower()
                         and "jumper" not in b["item"].lower())
    channels = iv["io_di"] + iv["io_do"] + iv["io_ai"] + iv["io_ao"]
    if channels:
        term = control_signalling(io_terminals=channels, terminal_make=g.get("terminal_make", sd["terminal_make"]),
                                  io_conductor_mm2=g.get("io_conductor_mm2", sd["io_conductor_mm2"]))
        log("terminals", term)
        for b in (term.value or {}).get("bom", []):
            add("Control and signalling", b["article"], b["item"], b["qty"], "no", "I/O channels", b["source"])
        qty_terms = sum(b["qty"] for b in (term.value or {}).get("bom", []) if b["item"].startswith("Terminal block"))
    sizes = {}
    for f in pv["feeders"]:
        if f.get("wire_ib_a") is None:
            continue
        if f.get("wire_in_a") is None:
            opens.append({"tag": f["tag"], "component": "internal_wiring", "rule": "R-REQ-11", "kind": "warning",
                          "point": "internal wiring not sized: no protective device rating for this feeder (star-delta kit)"})
            continue
        w = internal_wiring(ib_a=f["wire_ib_a"], in_a=f["wire_in_a"], ambient_c=pic,
                            insulation=str(g.get("wire_insulation", sd["wire_insulation"])),
                            circuits=int(g.get("wire_circuits") or 1), min_size_mm2=float(g["min_power_wire_mm2"]) if g.get("min_power_wire_mm2") is not None
                            else sd.get("min_power_wire_mm2"))
        log(f["tag"], w)
        f["internal_wire"] = (w.value or {}).get("wire")
        if w.status not in ("cannot_select", "invalid"):
            s = sizes.setdefault(f"{w.value['size_mm2']:g} mm²", [])
            s.append(f["tag"])
    for key, tags in sizes.items():
        add("Internal wiring", f"Lapp H07V-K {key}", "power wiring (metres not calculated)", "not calculated", "m",
            ", ".join(tags), "internal wiring (19)", make="Lapp")
    res.add("R-REQ-11", "relays, terminals and internal wiring from the I/O list and the feeders",
            f"{qty_relays} relay(s), {qty_terms} terminal(s), wire sizes {', '.join(sizes) or 'none'}", INFO)

    # R-REQ-10: incomer — design current × the incomer factor (owner 2026-10-16, decision M-1: an input, 1.5 by default
    # as the company template's main switchgear FOS, OWN-SWG-CALC 'U1_Main_Switchgear' L27)
    tmpl = cp_method()["main_fos"]
    factor = float(g["incomer_factor"]) if g.get("incomer_factor") is not None else float(tmpl["value"])
    res.add("R-REQ-10", "incomer factor (In ≥ design current × factor)",
            f"{factor:g}" + (" (designer's input)" if g.get("incomer_factor") is not None
                             else f" (company template, OWN-SWG-CALC '{tmpl['sheet']}' {tmpl['cell']})"), INFO)
    sel = [f for f in pv["feeders"] if f["status"] == "selected" and f.get("wire_ib_a") is not None]
    missing = [f["tag"] for f in pv["feeders"] if f not in sel and f["status"] != "excluded"]
    ib = round(sum(f["wire_ib_a"] * f["running"] for f in sel), 2)
    inc = None
    if not sel:
        res.add("R-REQ-10", "incomer design current", "no selected feeder to size from", WARN)
    else:
        res.add("R-REQ-10", "incomer design current = Σ running units (drive input current / DOL FLC), no diversity",
                " + ".join(f"{f['running']} × {f['wire_ib_a']:g} A ({f['tag']})" for f in sel) + f" = {ib:g} A"
                + (f"; not in the sum (not selected): {', '.join(missing)}" if missing else ""),
                WARN if missing else INFO)
        inc = _incomer(g, ib, pic, factor) if scope["incomer"] else None
        if inc is not None and g.get("incomer_series") == "3VA":
            res.add("R-REQ-34", "incomer series 3VA1 with the TM240 trip unit (component mccb_3va)",
                    f"{inc.value.get('article_no') if inc.value else inc.status}"
                    + ("" if not inc.value or inc.value.get("confirmed") else " — built from the catalogue structure: confirm with its data sheet"),
                    INFO, "owner 2026-10-20")
        if inc is not None:
            log("incomer", inc)
        if inc is None or inc.status in ("cannot_select", "invalid"):
            inc = None
        else:
            add("Incomer", inc.value["article_no"], _inc_text(inc.value), 1, "no", "panel", "MCCB (3)")
        res.add("R-REQ-10", "busbar sized", "not sized: component 8 waits for the 3VA manual and IEC 61439-1", WARN)

    # R-REQ-16: company kits and indicative prices
    kit_lines = [b for b in bom if b["source"] == "company kit (feeder_kit)"]
    res.add("R-REQ-16", "company practice: kits for star-delta and DOL accessories, indicative prices",
            f"{len(kit_lines)} company-kit line(s); DOL source {d['dol_source']}; accessories "
            f"{'on' if d['kit_accessories'] else 'off'}", INFO, "OWN-PROPEL-DOL / OWN-PROPEL-COST")

    # R-REQ-14: 24 V DC supply (10) and auxiliary switchgear (11)
    plc_a, plc_cpu, pr = g.get("plc_24v_a"), None, None
    families = {"omron": ("omron", None), "siemens_s7200smart": ("siemens", "s7-200smart"),
                "siemens_s71200g2": ("siemens", "s7-1200g2"), "siemens_s71500": ("siemens", "s7-1500-et200sp")}
    if g.get("plc_make") in families:
        make, family = families[g["plc_make"]]
        fb = g.get("cu_fieldbus") if any(m["starter"] == "VFD" for m in mv) else None
        pr = plc_select(di=iv["io_di"], do=iv["io_do"], ai=iv["io_ai"], ao=iv["io_ao"], fieldbus=fb, make=make, family=family,
                        fieldbus_devices=iv.get("io_pn") if fb == "profinet" else None,
                        ambient_c=g.get("panel_internal_c") if family else None, spare_pct=g.get("plc_spare_pct"),
                        cpu=g.get("plc_cpu"), memory_card_mb=g.get("plc_mc_mb"), io_min=g.get("plc_io_min"))
        log("PLC", pr)
        if g.get("plc_io_min"):
            res.add("R-REQ-36", "PLC I/O at least the client's final count per type (spare included)",
                    ", ".join(f"{k.upper()} {v}" for k, v in g["plc_io_min"].items()), INFO, "client specification")
        if pr.status not in ("cannot_select", "invalid"):
            plc_a = pr.value.get("supply_24v_a", pr.value.get("i24_a"))
            plc_cpu = pr.value["cpu"]
            for part in pr.value["parts"]:
                q_ = part.get("qty", 1)
                if not q_:
                    continue
                desc = part.get("model") or part["role"]
                if "di" in part:
                    desc = f"{part['role']}: {desc} ({part['di']:g} DI / {part['do']:g} DO)"
                else:
                    desc = f"{part['role']}: {desc}"
                add("PLC", part["article"], desc, q_, "no", "I/O list", part["source"])
    # R-REQ-23 / R-PWR-12 (owner 2026-10-16): the designer's 24 V row edits size the supply too, not only its check
    extra_dc = 0.0
    dc_ed = [e for e in (power_edits or []) if isinstance(e, dict) and e.get("dc")]
    if dc_ed:
        m0, c0 = cp_method(), cp_coil()
        pre = [{"key": "di", "item": "di", "qty": iv["io_di"], "per_unit": m0["di_a"]["value"]},
               {"key": "relays", "item": "relays", "qty": iv["io_do"], "per_unit": c0["i_ma"] / 1000},
               {"key": "plc", "item": "plc", "qty": 1, "per_unit": plc_a}]
        a0 = power_calc(voltage_v=g["voltage_v"], three_phase=[], single_phase=[], dc=pre)
        a1 = power_calc(voltage_v=g["voltage_v"], three_phase=[], single_phase=[], dc=pre, edits=dc_ed)
        if a0.status != "invalid" and a1.status != "invalid":
            extra_dc = round(a1.value["dc_load_a"] - a0.value["dc_load_a"], 4)
            res.add("R-REQ-23", "24 V supply sized with the designer's 24 V row edits",
                    f"{extra_dc:+g} A" + (" (a lower load does not make the supply smaller: it is sized on the rows the tool counts)"
                                          if extra_dc < 0 else ""), INFO)
    cp_in, cp_brand = g.get("smps_input", sd["smps_input"]), g.get("smps_brand") or sd["smps_brand"]
    # R-REQ-35 (owner 2026-10-20, RFQ part 5): a separate supply for the CPU and one for the I/O stations and field signals
    cpu_row = next((r for r in ((pr.value or {}).get("i24_rows") or []) if plc_cpu and r["item"] == plc_cpu), None) \
        if g.get("smps_split") == "cpu_io" and pr is not None else None
    split = None
    if g.get("smps_split") == "cpu_io" and scope["smps"] and scope["plc"]:
        if cpu_row is None or cpu_row.get("unit_a") is None:
            res.add("R-REQ-35", "24 V split: a supply for the CPU and one for the I/O",
                    "no CPU with a printed 24 V current in this panel (remote I/O only, or the CPU's current not held): one supply",
                    WARN, "owner 2026-10-20")
        else:
            cpu_a = round(cpu_row["unit_a"] * cpu_row["qty"], 4)
            c1 = control_power(plc_a=cpu_a, input=cp_in, brand=cp_brand, min_a=g.get("smps_cpu_min_a"))
            c2 = control_power(di=iv["io_di"], relays=iv["io_do"], plc_a=round(plc_a - cpu_a, 4), input=cp_in, brand=cp_brand,
                               other_a=max(extra_dc, 0.0), min_a=g.get("smps_io_min_a"))
            log("control power (CPU)", c1)
            log("control power (I/O)", c2)
            split = (c1, c2)
    cp = control_power(di=iv["io_di"], relays=iv["io_do"], plc_a=plc_a, input=cp_in, brand=cp_brand, other_a=max(extra_dc, 0.0),
                       min_a=g.get("smps_min_a")) \
        if scope["smps"] and scope["plc"] and split is None else None   # R-REQ-31: no 24 V supply listed (or nothing to feed)
    if cp is not None:
        log("control power", cp)
    smps = None
    if split is not None:
        c1, c2 = split
        bad = [c for c in split if c.status in ("cannot_select", "invalid")]
        if not bad:
            for c, who in ((c1, "the CPU"), (c2, "the I/O stations, inputs and relays")):
                add("Control power", f"{c.value['smps_brand']} {c.value['smps']}", f"24 V DC power supply {c.value['smps_a']:g} A for {who} "
                    f"(needs {c.value['required_a']:g} A)", 1, "no", who, "control power (10), R-REQ-35", make=c.value["smps_brand"])
            smps = f"{c1.value['smps']} + {c2.value['smps']}"
            res.add("R-REQ-35", "24 V split: a supply for the CPU and one for the I/O",
                    f"CPU {c1.value['load_a']:g} A → {c1.value['smps']} {c1.value['smps_a']:g} A; I/O {c2.value['load_a']:g} A → "
                    f"{c2.value['smps']} {c2.value['smps_a']:g} A", INFO, "owner 2026-10-20")
            cp = c2                                     # the pair as one 24 V source for the budget and the power calculation
            cp.value = {**c2.value, "smps": smps, "smps_a": c1.value["smps_a"] + c2.value["smps_a"],
                        "required_a": round(c1.value["required_a"] + c2.value["required_a"], 4),
                        "load_a": round(c1.value["load_a"] + c2.value["load_a"], 4),
                        "smps_efficiency": min(x for x in (c1.value.get("smps_efficiency"), c2.value.get("smps_efficiency")) if x)
                        if c1.value.get("smps_efficiency") and c2.value.get("smps_efficiency") else None,
                        "split": [{"for": "CPU", **{k: c1.value[k] for k in ("smps", "smps_a", "required_a", "load_a")}},
                                  {"for": "I/O", **{k: c2.value[k] for k in ("smps", "smps_a", "required_a", "load_a")}}]}
        else:
            cp = bad[0]
    elif cp is not None and cp.status not in ("cannot_select", "invalid"):
        smps = cp.value["smps"]
        add("Control power", f"{cp.value['smps_brand']} {smps}", f"24 V DC power supply {cp.value['smps_a']:g} A "
            f"(needs {cp.value['required_a']:g} A)", 1, "no", "PLC, I/O, relays", "control power (10)", make=cp.value["smps_brand"])
    aux = None
    if g.get("spd") or g.get("pmr"):
        aux = aux_switchgear(spd=g.get("spd_config", sd["spd_config"]) if g.get("spd") else None, spd_make=g.get("spd_make"),
                             spd_remote_signalling=g.get("spd_signalling"),
                             pmr=bool(g.get("pmr")), pmr_make=sd["pmr_make"] if g.get("pmr") else None,
                             fault_ka=g["fault_ka"])
        log("aux switchgear", aux)
        for dv in (aux.value or {}).get("devices", []):
            add("Auxiliary switchgear", dv["article"], f"{dv['device']} ({dv['rating']}, {dv['make']})", 1, "no",
                dv["circuit"], dv["source"], make=dv.get("make"))
    res.add("R-REQ-14", "24 V DC supply and auxiliary switchgear",
            f"supply {smps or 'not selected'}; surge arrester {'yes' if g.get('spd') else 'no'}; "
            f"phase monitoring relay {'yes' if g.get('pmr') else 'no'}", INFO if smps else WARN)

    # R-REQ-19: control circuit (component 25): supply, MCBs, E-stop / reset / phase lamps (company practice)
    units = {f["tag"]: f["qty"] for f in pv["feeders"] if f["status"] == "selected"}
    starters = {f["tag"]: f["starter"] for f in pv["feeders"]}
    coils = sum(q * (3 if starters[t] == "SD" else 1) for t, q in units.items() if starters[t] in ("DOL", "SD"))
    from core.drawing_tags import role_of
    ss_ct = sum(int(b["qty"]) for b in bom if b["group"] == "Feeders" and isinstance(b["qty"], (int, float))
                and any(starters.get(t) == "SS" for t in str(b["used_by"]).split(", "))
                and role_of(b["article"], b["description"]) == "contactor")     # audit 2026-10-17: a soft starter's line contactor
    coils += ss_ct
    lamps = sum(b["qty"] for b in bom if b["article"].startswith("XB7") and isinstance(b["qty"], (int, float)))
    # coil VA: the designer's value if given, else the catalogue power from the DOL selection (R-CC-05 / 06)
    coil_args = {"coils": coils, "coil_va": g.get("coil_va")} if g.get("coil_va") is not None else \
        {"coil_power": coil_loads(pv["feeders"])[0] + ([{"close_va": None, "hold_va": None, "qty": ss_ct}] if ss_ct else [])}
    ph_l = bool(g.get("phase_lamps"))            # audit 2026-10-17: E-stop, reset and phase lamps asked, not assumed
    cc = control_circuit(supply=g.get("control_supply") or sd["control_supply"], **coil_args,
                         lamps=lamps + (3 if ph_l else 0), lamp_va=g.get("lamp_va"), estop=int(bool(g.get("estop"))),
                         reset=int(bool(g.get("reset_pb"))), phase_lamps=ph_l)
    if not scope["control_transformer"]:          # R-REQ-31: no control transformer listed (a feeder kit fed from a main panel)
        cc.value = {**cc.value, "bom": [], "load_va": 0, "required_va": None, "transformer_va": None}
    log("control circuit", cc)
    for b in cc.value["bom"]:
        add("Control circuit", b["article"], b["description"], b["qty"], "no", "panel", b["source"], b.get("unit_price_inr"))
    if scope["control_transformer"]:
        res.add("R-REQ-19", "control circuit: supply, MCBs, emergency stop, reset, phase lamps",
                f"{coils} contactor coil(s), {lamps + (3 if ph_l else 0)} lamp(s); transformer "
                f"{(str(cc.value['transformer_va']) + ' VA') if cc.value['transformer_va'] else 'not sized (give coil and lamp VA)'}",
                INFO if cc.value["transformer_va"] or (g.get("control_supply") or sd["control_supply"]) != "transformer" else WARN)

    # R-REQ-23: power calculation (component power): AC per phase with single-phase loads balanced, and 24 V DC
    m_, coil_ = cp_method(), cp_coil()
    three, single = [], []
    for f in pv["feeders"]:
        if f["status"] != "selected" or not f.get("wire_ib_a"):
            continue
        src = "drive input current (PM240-2 data)" if f["starter"] == "VFD" else "motor FLC (component 1)"
        if (f.get("phases") or 3) == 1:
            single.append({"name": f"{f['tag']} {f['kw']:g} kW (single-phase)", "i_a": f["wire_ib_a"] * f["running"], "connection": "LN", "source": src})
        else:
            three.append({"tag": f["tag"], "description": f"{f['kw']:g} kW {f['starter']}" + (f" × {f['running']}" if f["running"] > 1 else ""),
                          "running": f["running"], "i_a": f["wire_ib_a"], "kw": f["kw"], "source": src,
                          "protection": protection_for(f["tag"], bom)})
    supply_ = g.get("control_supply") or sd["control_supply"]
    value["control_supply"] = supply_ if scope["control_transformer"] else None     # what was used (default: CC-1)
    how_ = next((f.get("how") for f in value.get("facts") or [] if f.get("input") == "control_supply"), None)
    value["control_supply_how"] = ("template" if how_ == "template" else "given") if g.get("control_supply") else "default"
    if cc.value.get("load_va"):
        part_ = any(r.get("total") is None for r in cc.value.get("load_rows", []))
        single.append({"key": "control", "name": ("control circuit (transformer primary, connected load; transformer losses not included)"
                                                  if supply_ == "transformer" else "control circuit (230 V)")
                       + (" — partial: a load has no VA" if part_ else ""),
                       "va": cc.value["load_va"], "connection": "LL" if supply_ == "transformer" else "LN",
                       "source": "control circuit (25): Σ holding + largest closing step + lamps", "group": "supply",
                       "kind": "Transformer" if supply_ == "transformer" else "Control circuit",
                       "kw": round(cc.value["load_va"] / 1000, 4),
                       "protection": next((f"{b['article']} — {b['description']}" for b in cc.value["bom"]
                                           if "primary" in b["description"] or "control circuit" in b["description"]), None)})
    dc_rows = [{"key": "di", "item": "digital inputs (company template)", "qty": iv["io_di"], "per_unit": m_["di_a"]["value"],
                "source": f"OWN-SWG-CALC '{m_['di_a']['sheet']}' {m_['di_a']['cell']}"},
               {"key": "relays", "item": "interface relay coils (one per output)", "qty": iv["io_do"], "per_unit": coil_["i_ma"] / 1000,
                "source": f"relay coil {coil_['coil_code']} p.{coil_['page']}"},
               {"key": "plc", "item": f"PLC {plc_cpu or ''} (CPU and modules, R-PLC-24)".replace("  ", " "), "qty": 1, "per_unit": plc_a,
                "source": "PLC selection" if plc_cpu else "designer input"}]
    not_counted = [f"{f['tag']} {f['kw']:g} kW {f['starter']} ({f['status']}: no current to count — add it with an edit)"
                   for f in pv["feeders"] if f["status"] != "selected"] + (["energy meter"] if g.get("meter") else []) + (["surge arrester"] if g.get("spd") else []) \
        + (["phase monitoring relay"] if g.get("pmr") else []) + (["HMI (not selected)"] if scope["plc"] else [])
    if not scope["plc"]:                       # R-REQ-31: without a PLC the tool counts no 24 V loads (the designer adds them)
        dc_rows = [] if scope["smps"] else None
        if scope["smps"]:
            not_counted.append("24 V loads of the template's supply (not in the held data: add them as 24 V rows)")
    tpl_smps = scope.get("smps_line") if g.get("template") and scope["smps"] and smps is None else None
    pw = power_calc(voltage_v=g["voltage_v"], three_phase=three, single_phase=single, dc=dc_rows,
                    dc_factor=m_["smps_fos"]["value"], dc_factor_source=f"OWN-SWG-CALC '{m_['smps_fos']['sheet']}' {m_['smps_fos']['cell']}",
                    dc_available_a=cp.value["smps_a"] if smps else scope.get("smps_a") if tpl_smps else None,
                    dc_supply=smps or tpl_smps,
                    dc_efficiency=cp.value.get("smps_efficiency") if smps else None, not_counted=not_counted,
                    main_fos=factor, frequency_hz=g.get("frequency_hz") or 50, edits=power_edits)
    log("power", pw)
    # a power edit that no longer fits the design (its load is gone) stops the power calculation only, shown with its undo
    power_error = next(c.value for c in pw.checks if c.verdict == "fail") if pw.status == "invalid" else None
    power = pw.value if pw.status not in ("cannot_select", "invalid") else None
    res.add("R-REQ-23", "power calculation: AC per phase (single-phase loads balanced) and 24 V DC" + (f" — {power_error}" if power_error else ""),
            f"L1 {power['i_l1_a']:.1f} / L2 {power['i_l2_a']:.1f} / L3 {power['i_l3_a']:.1f} A, imbalance {power['imbalance_pct']:g} %, "
            f"{power['s_kva']:.1f} kVA; " + (f"24 V {power['dc_load_a']:g} A × {power['dc']['factor']:g} = {power['dc_required_a']:g} A"
                                              if power.get("dc") else "no 24 V supply in this panel")
            if power else "not calculated", INFO if power else WARN)

    # R-REQ-26 (owner 2026-10-16): every calculation takes its I/O counts from the one I/O list — shown and checked
    io_trace = []

    def trace(what, count, used_in, value, ok):
        io_trace.append({"io": what, "count": count, "used_in": used_in, "value": value, "ok": ok})
    di, do_, ai, ao = iv["io_di"], iv["io_do"], iv["io_ai"], iv["io_ao"]
    dcq = {r["key"]: r for r in ((power or {}).get("dc") or {}).get("rows", [])}   # the 24 V rows as calculated (edits applied)

    def dc_used(key, count, per):
        r_ = dcq.get(key)
        if r_ is None:
            return f"{count} × {per:g} A = {count * per:.4f} A", True
        if r_.get("edited") and r_["qty"] != count:
            return f"your power edit: {r_['qty']:g} (the I/O list has {count}) — undo it or edit the I/O list", False
        return f"{r_['qty']:g} × {r_['per_unit']:g} A = {r_['total']:.4f} A", r_["qty"] == count
    v_, ok_ = dc_used("di", di, m_["di_a"]["value"])
    trace("DI", di, "24 V DC load: digital inputs (company template)", v_, ok_)
    trace("DO", do_, "interface relays (one per output)", f"{qty_relays} relay(s)", qty_relays == do_ or not do_)
    v_, ok_ = dc_used("relays", do_, coil_["i_ma"] / 1000)
    trace("DO", do_, "24 V DC load: relay coils", v_, ok_)
    trace("DI + DO + AI + AO", di + do_ + ai + ao, "I/O terminals (one per channel)", f"{qty_terms} terminal(s)", qty_terms >= di + do_ + ai + ao)
    if pr is not None and pr.status not in ("cannot_select", "invalid"):
        pv_ = pr.value
        for t, n_ in (("DI", di), ("DO", do_), ("AI", ai), ("AO", ao)):
            if n_ or pv_.get(f"required_{t.lower()}"):
                req_, cap_ = pv_.get(f"required_{t.lower()}"), pv_.get(f"capacity_{t.lower()}")
                trace(t, n_, f"PLC {t} channels (with spare)", f"{n_} → {req_} needed, {cap_} available on {pv_['cpu']}"
                      + (f" + {pv_['n_modules']} module(s)" if pv_.get("n_modules") else ""),
                      req_ is not None and cap_ is not None and req_ >= n_ and cap_ >= req_)
    if iv["io_pn"]:
        trace("PN", iv["io_pn"], "drives on the fieldbus", ", ".join(r["name"] for r in iv["bus"]), True)
    if iv["io_safety"]:
        trace("STO", iv["io_safety"], "safe torque off signals", ", ".join(r["name"] for r in iv["safety"]), True)
    if not scope["plc"]:
        io_trace = []                             # R-REQ-31: no PLC, no I/O to carry
    bad_ = [t for t in io_trace if not t["ok"]]
    if io_trace:
        res.add("R-REQ-26", "every calculation uses the I/O list's counts (relays, terminals, 24 V load, PLC channels)",
                "; ".join(f"{t['io']} {t['count']} → {t['used_in']}: {t['value']}" for t in io_trace)
                + (" — MISMATCH: " + ", ".join(t["used_in"] for t in bad_) if bad_ else ""), WARN if bad_ else PASS)

    # R-REQ-10 (QA 2026-10-16, L6): the incomer carries the largest phase, single-phase loads included
    if power and inc:
        top = max(power["i_l1_a"], power["i_l2_a"], power["i_l3_a"])
        if abs(top - ib) > 1e-9 and (top > ib or power_edits):   # a power edit that lowers the load makes it smaller too
            inc2 = _incomer(g, round(top, 2), pic, factor)
            log("incomer", inc2)
            if inc2.status in ("cannot_select", "invalid"):
                res.add("R-REQ-10", "incomer for the largest phase (single-phase loads included)",
                        f"{top:.2f} A: no MCCB found — incomer {inc.value['article_no']} kept for {ib:g} A", WARN)
            else:
                if inc2.value["article_no"] != inc.value["article_no"]:
                    for b in bom:
                        if b["group"] == "Incomer":
                            b.update(article=inc2.value["article_no"], description=_inc_text(inc2.value), make=None)
                res.add("R-REQ-10", "incomer for the largest phase (single-phase loads included)",
                        f"{ib:g} A → {top:.2f} A on the largest phase: {inc2.value['article_no']} (In {inc2.value['in_a']:g} A)"
                        + (" — changed" if inc2.value["article_no"] != inc.value["article_no"] else " — same breaker"), INFO)
                inc, ib = inc2, round(top, 2)
    # R-REQ-25 (QA 2026-10-16, H4): the incomer against the outgoing protective devices
    if inc:
        outs = [(f["tag"], f["device_in_a"]) for f in sel if f.get("device_in_a")]
        unknown = [f["tag"] for f in sel if not f.get("device_in_a")]
        big = [(t, a_) for t, a_ in outs if a_ >= inc.value["in_a"]]
        res.add("R-REQ-25", "incomer rated above every outgoing protective device (selectivity itself is not verified: "
                            "no Siemens selectivity table held — pending source)",
                (f"incomer In {inc.value['in_a']:g} A ≤ " + ", ".join(f"{t} {a_:g} A" for t, a_ in big)
                 + ": a fault on that feeder can trip the incomer — choose a larger incomer or a smaller outgoing device"
                 if big else f"incomer In {inc.value['in_a']:g} A > largest outgoing device "
                 + (f"{max(a_ for _, a_ in outs):g} A" if outs else "(none rated)"))
                + (f"; rating not held for {', '.join(unknown)}" if unknown else ""),
                WARN if big or unknown else INFO)

    # R-REQ-12: metering
    met = None
    if g.get("meter"):
        if inc is None:
            res.add("R-REQ-12", "energy meter on the incomer", "not selected: no incomer", WARN)
        else:
            met = metering(circuit_a=inc.value["in_a"], ct_make=g["ct_make"],
                           communication=g.get("meter_comm"), ambient_c=pic, meter_supply=g.get("meter_supply"))
            log("metering", met)
            if met.status in ("cannot_select", "invalid"):
                met = None
            else:
                mv_ = met.value
                add("Metering", mv_.get("meter_article") or mv_["meter_article_pattern"],
                    f"{mv_['meter']} energy meter" + ("" if mv_.get("meter_article") else " (complete the article no.)"),
                    1, "no", "incomer", "metering (15)" + (", LV 10 p.10/32" if mv_.get("meter_article") else ""))
                if mv_.get("comm_module"):
                    add("Metering", mv_["comm_module"], "PROFINET module for the meter", 1, "no", "incomer", "metering (15)")
                add("Metering", mv_["ct_designation"], f"Current transformer {mv_['ct_ratio']}", mv_["ct_qty"], "no",
                    "incomer", "metering (15)", make={"rishabh": "Rishabh Instruments", "selec": "Selec Controls"}.get(g["ct_make"], g["ct_make"]))
                # QA 2026-10-16 (M3): how far down its range the CT reads this machine (accuracy at low current not checked)
                if power:
                    top_ = max(power["i_l1_a"], power["i_l2_a"], power["i_l3_a"])
                    pct = top_ / mv_["ct_primary_a"] * 100
                    res.add("R-REQ-12", "meter CT loading at full machine load (accuracy class at low current not checked: "
                                        "IEC 61869-2 not held, decision RQ-10)",
                            f"{top_:.2f} A on a {mv_['ct_ratio']} CT = {pct:.1f} % of its primary"
                            + (" — the meter reads this machine at the bottom of the CT range; consider a smaller CT ratio" if pct < 20 else ""),
                            WARN if pct < 20 else INFO)
            res.add("R-REQ-12", "energy meter on the incomer", met.value["ct_designation"] if met else "not selected",
                    INFO if met else WARN)

    # R-REQ-13: blocked components
    not_selected = list(prm["blocked"]) + [n for n in pv["not_selected"] if n not in NOT_BUILT]
    # R-REQ-17: one consolidated list of what is not selected, with category and reason
    detail = [{"item": n.split(":")[0], "category": "component not built", "why": n.split(":", 1)[1].strip() if ":" in n else n}
              for n in prm["blocked"]]
    detail += [{"item": n, "category": "not selected for this panel", "why": "question open"} for n in pv["not_selected"]
               if n not in NOT_BUILT]
    for o in opens:
        if o["kind"] == "refused" or any(w in o["point"] for w in ("not held", "not sized", "not selected", "not added")):
            detail.append({"item": f"{o['tag']}: {o['point'].split(':')[0][:90]}", "category": "not selected for this panel",
                           "why": f"{o['component']} {o['rule']}: {o['point'][:160]}"})
    detail += [{"item": n, "category": "in the company drawing, no selection component yet",
                "why": "listed in drawing AVELCPSDL08WPLC BOM pp.14-15 (OWN-PROPEL-SCH160)"} for n in prm["control_devices_not_built"]]
    detail += [{"item": n.split(" (owner")[0], "category": "out of scope", "why": n} for n in prm["out_of_scope"]]
    res.add("R-REQ-17", "everything not selected, in one list",
            ", ".join(f"{sum(1 for d_ in detail if d_['category'] == c)} {c}" for c in dict.fromkeys(x["category"] for x in detail)),
            INFO, "OWN-PROPEL-SCH160 pp.14-15")
    for n in not_selected:
        add("Not selected", "", n, "", "", "", "")
    fill_makes(bom)
    # R-REQ-29 (owner 2026-10-16): a template's lines are the BOM; the engine's own selection checks them
    tpl_info, rule_bom, tpl_checks = None, None, []
    if g.get("template"):
        from core import templates as T_
        t_ = T_.get(g["template"])
        rule_bom = bom
        bom = T_.bom(g["template"], motor_tag=mv[0].get("tag") or "M1")
        need_a = round(ib * factor, 1) if inc else None

        def tcheck(what, have, need, unit, src):
            ok_ = None if have is None or not need else have >= need     # nothing needed / not sized → not checked, never a pass
            tpl_checks.append({"what": what, "template": have, "needed": need or None, "unit": unit, "ok": ok_, "source": src})
        # R-REQ-31: a check only for what the template lists
        tl = next((l for l in bom if l["group"] == "Incomer" and T_.rating_a(l)), None)
        if scope["incomer"]:
            tcheck("Incomer MCCB", T_.rating_a(tl) if tl else None, need_a, "A", "R-REQ-10 (design current × incomer factor)")
        sm = next((l for l in bom if l["group"] == "Control power"), None)
        if sm is not None:
            need_dc = cp.value["required_a"] if cp is not None and cp.status not in ("cannot_select", "invalid") \
                else (power or {}).get("dc_required_a")
            tcheck("24 V supply", T_.rating_a(sm), need_dc, "A", "R-CP (24 V load × 1.25)")
        tr = next((l for l in bom if "control transformer" in l["description"].lower()), None)
        if tr is not None:
            va = re.search(r"(\d+)\s*VA", tr["description"])
            tcheck("Control transformer", float(va.group(1)) if va else None, (cc.value or {}).get("required_va"), "VA", "R-CC (connected VA × 1.5)")
        fails_ = [c for c in tpl_checks if c["ok"] is False]
        res.add("R-REQ-29", f"template {t_['title']} ({t_['ref']} sheet '{t_['sheet']}'): {len(bom)} lines are the BOM; checked against the rules",
                "; ".join(f"{c['what']} {c['template'] if c['template'] is not None else 'rating not printed'}"
                          + (f" {c['unit']} {'≥' if c['ok'] else '<'} {c['needed']:g} {c['unit']} needed" if c["ok"] is not None else " — not checked")
                          for c in tpl_checks), WARN if fails_ else PASS, t_["ref"])
        tpl_info = {"id": t_["id"], "title": t_["title"], "ref": t_["ref"], "sheet": t_["sheet"], "family": t_["family"]}
    # R-REQ-21: the designer's edits to this machine's BOM, checked like project edits (R-PRJ-17), original kept
    n_edits = 0
    post = {}
    pre_edit_bom = [dict(b) for b in bom]
    if edits:
        recs = []
        for i, e in enumerate(edits, 1):
            if not isinstance(e, dict):
                return res.invalid(f"edit {i} is not an edit")
            chk = bom_edit.check(e)
            if not chk["ok"]:
                return res.invalid(f"edit {i}: {chk['notes']}")
            recs.append({**e, "id": e.get("id", i), "panel": "machine", "line": e.get("line") or {},
                         "make": e.get("make") or chk.get("make"), "check": chk, "proposed_by": e.get("proposed_by", "designer")})
        bom_tail = [b for b in bom if b["group"] == "Not selected"]
        bom, unmatched = bom_edit.apply([b for b in bom if b["group"] != "Not selected"], recs, "machine")
        for b in bom:
            b.setdefault("unit_price_inr", None)          # added lines carry no company price
        bom = fill_makes(bom) + bom_tail
        n_edits = len(recs)
        res.add("R-REQ-21", "designer edits applied (checked against the parts catalog, original kept)",
                f"{n_edits - len(unmatched)} applied" + (f"; {len(unmatched)} match no line" if unmatched else ""),
                WARN if unmatched else INFO)
        if not g.get("template"):
            post = _after_edits(res, g, recs, pre_edit_bom, bom, pv, sel, three, single, dc_rows, not_counted, power_edits, factor,
                                m_, cc, coils, smps, cp, inc, qty_relays, io_trace, iv, scope, log)
    res.add("R-REQ-13", "components still blocked", f"{len(prm['blocked'])} listed as not selected", INFO)
    d_all = {k: x for k, x in {**d, **sd}.items() if k not in g and k not in ASKED_NOW}
    res.add("R-REQ-08", "panel defaults used (not asked)",
            ", ".join(f"{k} = {x}" for k, x in d_all.items()) + (", 3-phase supply" if phases == 3 else ""), INFO)

    single = len(mv) == 1
    feeder = pv["feeders"][0]
    arts = {x["category"]: x["part_number"] for x in feeder.get("vfd_bom") or []} if single else {}
    dol_dev = (feeder["devices"] or "").split(" + ") if single and mv[0]["starter"] == "DOL" \
        and feeder["status"] == "selected" else []
    ss_dev = (feeder["devices"] or "").split(" + ") if single and mv[0]["starter"] == "SS" \
        and feeder["status"] == "selected" else []
    starters = {m["starter"] for m in mv}
    choices = (["starter", "duty"] + (["drive protection", "control unit", "memory card"] if "VFD" in starters else [])
               + (["DOL source", "kit accessories"] if starters & {"DOL", "SD"} else []) + ["cable make / installation",
               "panel temperature", "PLC family", "24 V supply make"] + (["CT make"] if g.get("meter") else [])
               + (["surge arrester make"] if g.get("spd") else []) + ["control supply"])
    res.add("R-REQ-22", "alternatives for a BOM line = the design choices behind it, selected again (linked parts follow)",
            ", ".join(choices), INFO)
    # QA 2026-10-16 (M2): a feeder that could not be selected leaves the design incomplete — say so, with the reason
    incomplete = [{"tag": f["tag"], "kw": f["kw"], "starter": f["starter"], "status": f["status"],
                   "reason": next((o["point"] for o in opens if o.get("tag") == f["tag"] and o.get("kind") == "refused"), f["status"])}
                  for f in pv["feeders"] if f["status"] not in ("selected", "excluded")]
    if incomplete:
        res.add("R-REQ-10", "design complete: every motor feeder selected",
                "; ".join(f"{x['tag']} {x['kw']:g} kW {x['starter']} not selected — {x['reason'][:140]}" for x in incomplete), WARN)
    value["incomplete"] = incomplete
    value.update({"scope": scope, "scope_plc": int(scope["plc"]), "scope_smps": int(scope["smps"]),
                  "scope_incomer": int(scope["incomer"]), "scope_ct": int(scope["control_transformer"])})
    if tpl_info:
        value.update({"template": tpl_info, "rule_bom": rule_bom, "template_checks": tpl_checks,
                      "template_lines": sum(1 for b in bom if b.get("status") == "template"),
                      "template_incomer_a": next((c["template"] for c in tpl_checks if c["what"] == "Incomer MCCB"), None),
                      "template_fails": sum(1 for c in tpl_checks if c["ok"] is False)})
    value.update({"selected": True, "load_list": load_list, "n_edits": n_edits, "power": power, "power_error": power_error, "flc_a": feeder["flc_a"] if single else None,
                  "power_module": arts.get("Power Module"), "protection_device": arts.get("Protection"),
                  "control_unit": arts.get("Control Unit"), "memory_card": arts.get("Memory Card"),
                  "operator_panel": arts.get("Operator Panel"),
                  "soft_starter": ss_dev[0] if ss_dev else None,
                  "mpcb": dol_dev[0] if dol_dev else None, "contactor": dol_dev[1] if len(dol_dev) > 1 else None,
                  "incomer": inc.value["article_no"] if inc else None, "incomer_in_a": inc.value["in_a"] if inc else None,
                  "incomer_ib_a": ib if sel else None, "ct": met.value["ct_designation"] if met else None,
                  "qty_relays": qty_relays, "qty_io_terminals": qty_terms, "smps": smps, "plc_cpu": plc_cpu,
                  "transformer_va": cc.value["transformer_va"],
                  "plc_24v_calc_a": plc_a if plc_cpu else None,
                  "spd_article": (aux.value or {}).get("spd") if aux else None,
                  "pmr_article": (aux.value or {}).get("pmr") if aux else None,
                  "n_bom_lines": sum(1 for b in bom if b["group"] != "Not selected"), "n_open": len(opens),
                  "indicative_inr": round(sum(b["unit_price_inr"] * b["qty"] for b in bom if b["unit_price_inr"] is not None
                                              and isinstance(b["qty"], (int, float))), 2),
                  "n_priced": sum(1 for b in bom if b["unit_price_inr"] is not None),
                  **{k: iv[k] for k in ("io_di", "io_do", "io_ai", "io_ao", "io_pn", "io_safety")},
                  "vfd_bom": feeder.get("vfd_bom") or [] if single else [],
                  "vfd_boms": [{"tag": f["tag"], "qty": f["qty"], "items": f["vfd_bom"]} for f in pv["feeders"]
                               if f.get("vfd_bom")],
                  "bom": bom, "feeders": pv["feeders"], "open_points": opens, "not_selected": not_selected,
                  "not_selected_detail": detail, "n_not_selected": len(detail),
                  "io_list": iv["io_list"], "io_inputs": iv["inputs"], "io_outputs": iv["outputs"], "io_bus": iv["bus"],
                  "io_safety_list": iv["safety"], "io_trace": io_trace, "design_logic": logic})
    value.update(post)                              # what the BOM edits changed downstream (_after_edits)
    res.add("R-REQ-07", "selection run on the confirmed facts",
            f"{len(mv)} motor line(s): {len(opens)} open point(s)", WARN if opens else PASS)
    res.basis = "chained components"
    return res


def _incomer(g: dict, ib: float, pic: float, factor: float):
    """R-REQ-34 (owner 2026-10-20): the incomer from the series answered — 3VA1 with TM240 (component mccb_3va) or 3VM
    with TM210 / TM220 (component mccb)."""
    if g.get("incomer_series") == "3VA":
        return mccb_3va(ib_a=ib, fault_ka=g["fault_ka"], ambient_c=pic, voltage_v=g["voltage_v"], margin=factor,
                        breaking_basis=g.get("breaking_basis"))
    return mccb(ib_a=ib, fault_ka=g["fault_ka"], ambient_c=pic, voltage_v=g["voltage_v"], margin=factor,
                release=g.get("incomer_release"), breaking_basis=g.get("breaking_basis"))


def _inc_text(v: dict) -> str:
    """The incomer's BOM line: frame, rating, trip unit with its setting (owner 2026-10-20, RFQ part 1: the client asks
    for an adjustable release — the line says which one and where it is set), breaking class and capacity."""
    rel = v.get("release") or ""
    setting = f" (Ir {v['ir_range']}, set {v['ir_set_a']:g} A)" if v.get("ir_range") and "fixed" not in str(v["ir_range"]) else ""
    ser = v.get("series") or "3VM"
    if ser == "3VA" and not v.get("ir_range"):
        setting = f" (Ir adjustable, set {v['ir_set_a']:g} A; range on its data sheet)"
    return (f"Incomer MCCB {ser}, In {v['in_a']:g} A, {rel}{setting}, class {v['breaking_class']} (Icu {v['icu_ka']:g} kA)"
            if rel else f"Incomer MCCB {ser}, In {v['in_a']:g} A, class {v['breaking_class']} (Icu {v['icu_ka']:g} kA)")


def _va_of(b) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*VA", str(b["description"])) if b else None
    return float(m.group(1)) if m else None


def _after_edits(res, g, recs, before, after, pv, sel, three, single, dc_rows, not_counted, power_edits, factor, m_, cc, coils,
                 smps, cp, inc, qty_relays, io_trace, iv, scope, log) -> dict:
    """Audit 2026-10-17 (owner: "fix it"): the designer's BOM edits are applied last, so everything worked out from the BOM is
    worked out again from the edited BOM — the power calculation's protection column, the contactor coils of the control
    circuit, the 24 V supply and the incomer (with their ratings where the held data has them; never guessed), the incomer
    checks, the relay count and the feeders' device text. Returns the value fields to update."""
    from core.drawing_tags import role_of
    from components.mccb.select import _articles
    from components.control_power.select import _smps
    gone_ = lambda b: isinstance(b["qty"], (int, float)) and b["qty"] <= 0
    live = [b for b in after if b["group"] != "Not selected" and not gone_(b)]
    q = lambda b: b["qty"] if isinstance(b["qty"], (int, float)) else 0
    post, said = {}, []
    # feeders: the device text follows replacements and removals; a feeder left without a starter is flagged
    swap = {str(e["line"].get("article")): e.get("article") for e in recs if e.get("action") == "replace" and e.get("line")}
    gone = {str(e["line"].get("article")) for e in recs if e.get("action") == "remove" and e.get("line")}
    starter_roles = ("contactor", "pm", "ss")
    feeders = []
    for f in pv["feeders"]:
        f = dict(f)
        txt = str(f.get("devices") or "")
        for a, b_ in swap.items():
            if a and a in txt:
                txt = txt.replace(a, f"{b_} (edited)")
        for a in gone:
            if a and a in txt:
                txt = txt.replace(a, f"{a} (removed)")
        f["devices"] = txt
        mine = lambda bom_: [b for b in bom_ if f["tag"] in str(b.get("used_by")).split(", ") and b["group"] == "Feeders" and not gone_(b)]
        had = any(role_of(b["article"], b["description"]) in starter_roles for b in mine(before))
        has = any(role_of(b["article"], b["description"]) in starter_roles for b in mine(live))
        if had and not has:
            res.add("R-REQ-21", f"{f['tag']}: starter after the BOM edits",
                    f"{f['tag']} has no contactor, drive or soft starter left — its I/O (running / tripped / run) and its coil "
                    "stay in the design until you edit the I/O list or undo the edit", WARN)
        feeders.append(f)
    post["feeders"] = feeders
    # contactor coils actually in the BOM → the control transformer
    ct = lambda bom_: sum(int(q(b)) for b in bom_ if b["group"] == "Feeders" and not gone_(b)
                          and role_of(b["article"], b["description"]) == "contactor")
    d_coils = ct(after) - ct(before)
    tr_line = next((b for b in live if b["group"] == "Control circuit" and "control transformer" in b["description"].lower()), None)
    tr_was = next((b for b in before if b["group"] == "Control circuit" and "control transformer" in b["description"].lower()), None)
    need_va = (cc.value or {}).get("required_va")
    if d_coils:
        said.append(f"contactor coils {coils} → {coils + d_coils}")
        if g.get("coil_va") is not None:
            cc2 = control_circuit(supply=g.get("control_supply"), coils=max(coils + d_coils, 0), coil_va=g["coil_va"],
                                  lamps=sum(int(q(b)) for b in live if str(b["article"]).startswith("XB7")),
                                  lamp_va=g.get("lamp_va"), estop=int(bool(g.get("estop"))), reset=int(bool(g.get("reset_pb"))),
                                  phase_lamps=bool(g.get("phase_lamps")))
            need_va = (cc2.value or {}).get("required_va")
            for r_ in single:
                if r_.get("key") == "control" and (cc2.value or {}).get("load_va"):
                    r_["va"], r_["kw"] = cc2.value["load_va"], round(cc2.value["load_va"] / 1000, 4)
        else:
            res.add("R-REQ-21", "control transformer after the BOM edits",
                    f"the edits change the contactor coils by {d_coils:+d}: give the coil VA to size the transformer on the edited BOM", WARN)
    if tr_was and not tr_line:
        post["transformer_va"] = None
        said.append("control transformer removed")
        res.add("R-REQ-21", "control transformer after the BOM edits",
                "the control transformer is removed: the 230 V control circuit has no supply — undo, or choose phase-neutral", WARN)
    elif tr_line:
        have = _va_of(tr_line)
        post["transformer_va"] = have
        if have and need_va and have < need_va:
            res.add("R-REQ-21", "control transformer after the BOM edits", f"{have:g} VA < {need_va:g} VA needed", WARN)
    # relays in the BOM
    rel = sum(int(q(b)) for b in live if b["group"] == "Control and signalling" and "relay" in b["description"].lower()
              and "jumper" not in b["description"].lower())
    if rel != qty_relays:
        said.append(f"relays {qty_relays} → {rel}")
        post["qty_relays"] = rel
        for t in io_trace:
            if t["used_in"] == "interface relays (one per output)":
                t["value"], t["ok"] = f"{rel} relay(s) (BOM edit)", rel == iv["io_do"] or not iv["io_do"]
        post["io_trace"] = io_trace
    # the 24 V supply in the BOM
    sm = next((b for b in live if b["group"] == "Control power"), None)
    dc_avail, dc_sup = (cp.value["smps_a"] if smps else None), smps
    if smps and (sm is None or smps not in str(sm["article"])):
        if sm is None:
            dc_avail, dc_sup = None, None
            said.append("24 V supply removed")
        else:
            norm = lambda x: str(x).replace(" ", "").upper()
            hit = next((r for r in _smps()["rows"] if norm(r["model"]) in norm(sm["article"])), None)
            dc_avail, dc_sup = (hit["i_out_a"] if hit else None), str(sm["article"])
            said.append(f"24 V supply → {sm['article']}" + (f" ({hit['i_out_a']:g} A)" if hit else " (rating not held)"))
            if hit is None:
                res.add("R-REQ-21", "24 V supply after the BOM edits",
                        f"{sm['article']}: its current rating is not in the held data — the 24 V check is not done", WARN)
        post["smps"] = dc_sup
    # the incomer in the BOM
    il = next((b for b in live if b["group"] == "Incomer"), None)
    if inc and (il is None or str(il["article"]) != inc.value["article_no"]):
        if il is None:
            inc_art, inc_in = None, None
            said.append("incomer removed")
        else:
            hit = next((r for r in _articles()["rows"] if r["article"] == str(il["article"])), None)
            m2 = re.search(r"\bIn\s*(\d+(?:\.\d+)?)\s*A", str(il["description"]))
            inc_art, inc_in = str(il["article"]), (float(hit["in_a"]) if hit else float(m2.group(1)) if m2 else None)
            said.append(f"incomer → {inc_art}" + (f" (In {inc_in:g} A)" if inc_in else " (rating not held)"))
            if inc_in is None:
                res.add("R-REQ-21", "incomer after the BOM edits",
                        f"{inc_art}: its rating is not in the held data — the incomer checks are not done", WARN)
        post.update({"incomer": inc_art, "incomer_in_a": inc_in})
        if inc_in is not None:
            need = round(sum(f["wire_ib_a"] * f["running"] for f in sel) * factor, 2)
            outs = [(f["tag"], f["device_in_a"]) for f in sel if f.get("device_in_a")]
            big = [(t, a_) for t, a_ in outs if a_ >= inc_in]
            res.add("R-REQ-25", "edited incomer rated above every outgoing protective device",
                    (f"In {inc_in:g} A ≤ " + ", ".join(f"{t} {a_:g} A" for t, a_ in big)) if big else f"In {inc_in:g} A — ok",
                    WARN if big else INFO)
            res.add("R-REQ-10", "edited incomer ≥ design current × factor", f"In {inc_in:g} A vs {need:g} A needed",
                    WARN if inc_in < need else INFO)
    # the power calculation again, on the edited BOM
    for r_ in three:
        r_["protection"] = protection_for(r_["tag"], live)
    pw = power_calc(voltage_v=g["voltage_v"], three_phase=three, single_phase=single, dc=dc_rows,
                    dc_factor=m_["smps_fos"]["value"], dc_factor_source=f"OWN-SWG-CALC '{m_['smps_fos']['sheet']}' {m_['smps_fos']['cell']}",
                    dc_available_a=dc_avail, dc_supply=dc_sup,
                    dc_efficiency=cp.value.get("smps_efficiency") if smps and dc_sup == smps else None, not_counted=not_counted,
                    main_fos=factor, frequency_hz=g.get("frequency_hz") or 50, edits=power_edits)
    log("power (after the BOM edits)", pw)
    post["power"] = pw.value if pw.status not in ("cannot_select", "invalid") else None
    post["power_error"] = next(c.value for c in pw.checks if c.verdict == "fail") if pw.status == "invalid" else None
    res.add("R-REQ-21", "edits carried into power, control circuit, 24 V supply, incomer and relays",
            "; ".join(said) or "protection column and device text updated (no rating changed)", INFO)
    return post


from core.guard import guarded  # noqa: E402  (fail closed on bad input: NaN, inf, negative, text)

select = guarded(select)
