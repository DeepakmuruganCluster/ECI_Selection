"""G6 checks of the Siemens IC 10 · 2026 and LV 10 · 2026 tables (data/makers/siemens) against each other and the own database."""
import re
from pathlib import Path

import yaml

from core.data import data_file
from core.provenance import load_sourced_table

ROOT = Path(__file__).resolve().parents[1]
POLES = {"1P": 1, "2P": 2, "3P": 3, "4P": 4, "1P+N": 2, "3P+N": 4}


def rows(name, fields=("article",)):
    return load_sourced_table(data_file(name), fields)["rows"]


def test_tables_load_with_provenance():
    for n, f in (("ic10_3rt2_contactors.yaml", ("article", "size", "uc_v")), ("ic10_3rt2_coil_power.yaml", ("size", "types", "coil")),
                 ("lv10_mcb.yaml", ("article", "series", "breaking_capacity", "poles", "curve", "in_a")),
                 ("lv10_rccb.yaml", ("article", "type", "poles", "idn_ma", "in_a")), ("lv10_5sd74_type2.yaml", ("article", "system", "circuit"))):
        assert rows(n, f)


def test_every_dol_contactor_is_in_ic10_with_the_same_size():
    ic = {r["article"]: r for r in rows("ic10_3rt2_contactors.yaml")}
    for r in yaml.safe_load(data_file("siemens_type2_400v.yaml").read_text())["rows"]:
        if r.get("contactor"):
            assert r["contactor"] in ic, r
            assert ic[r["contactor"]]["size"] == r["size"].split("/")[1], (r, ic[r["contactor"]]["size"])
            assert ic[r["contactor"]]["uc_v"] == "230", r


def test_every_contactor_type_has_a_24v_dc_version_and_coil_power():
    ic = rows("ic10_3rt2_contactors.yaml")
    coil = rows("ic10_3rt2_coil_power.yaml", ("size", "types", "coil"))
    for t in sorted({r["type"] for r in ic}):
        dc = [r for r in ic if r["type"] == t and r["operation"] != "AC" and r["uc_v"] in ("24", "20 ... 33")]
        assert dc, t
        assert any(t in c["types"] and c["coil"] != "AC" for c in coil), t
        assert any(t in c["types"] and c["coil"] == "AC" for c in coil), t


def test_mcb_series_carry_their_printed_breaking_capacity():
    ka = {"5SL3": "4.5 kA", "5SL6": "6 kA", "5SL4": "10 kA", "5SY6": "6 kA", "5SY4": "10 kA", "5SP4": "10 kA", "5SY7": "15 kA", "5SY8": "25 kA"}
    for r in rows("lv10_mcb.yaml"):
        assert r["breaking_capacity"] == ka[r["series"]], r
        assert r["article"].startswith(r["series"]) and r["page"] in range(280, 308), r


def test_own_siemens_mcbs_and_rccbs_match_lv10():
    """The 164 Siemens MCB and 24 RCCB rows of the own database (India 'RC' / 'CC' suffix) equal LV 10 on poles, curve / IΔn, In."""
    mcb = {r["article"].replace("-", ""): r for r in rows("lv10_mcb.yaml")}
    rccb = {r["article"].replace("-", ""): r for r in rows("lv10_rccb.yaml")}
    own = yaml.safe_load(data_file("own_mcb.yaml").read_text())["rows"]
    n = 0
    for r in (x for x in own if x["make"] == "Siemens"):
        base = re.fullmatch(r"(5S[LYP]\d{5})[A-Z]*", r["article"].strip()).group(1)
        lv = mcb[base]
        assert (POLES[lv["poles"]], lv["curve"], float(lv["in_a"])) == (r["poles"], r["curve"], float(r["in_a"])), (r, lv)
        n += 1
    assert n == 164
    own = yaml.safe_load(data_file("own_rccb.yaml").read_text())["rows"]
    m = 0
    for r in (x for x in own if x["make"] == "Siemens"):
        lv = rccb[re.fullmatch(r"(5SV\d{5})[A-Z0-9]*", r["article"].strip()).group(1)]
        assert (POLES[lv["poles"]], lv["idn_ma"], lv["in_a"]) == (r["poles"], r["idn_ma"], r["in_a"]), (r, lv)
        m += 1
    assert m == 24


def test_spd_type2_values_are_consistent():
    for r in rows("lv10_5sd74_type2.yaml", ("article",)):
        assert r["sc_strength_ka"] == 25
        if r["imax_ln_ka"]:
            assert r["imax_ln_ka"] >= r["in_ln_ka"]
        assert r["article"].endswith("-1") == r["remote_signalling"] or r["article"] == "5SD7483-5"


def test_s7200smart_rows_are_printed_on_their_pages():
    """G6: every article and current of s7200smart_modules.yaml is in the PDF text of its page (or the next one)."""
    import pypdfium2 as pdfium
    from core.provenance import register
    pdf = pdfium.PdfDocument(str(ROOT / "sources" / register()["SIE-S7-200SMART-SYS"]["file"]))
    text = lambda n: re.sub(r"\s+", "", pdf[n - 1].get_textpage().get_text_range().replace("‑", "-"))
    for r in rows("s7200smart_modules.yaml", ("article", "model", "kind")):
        t = text(r["page"]) + text(r["page"] + 1)
        want = [r["article"]] + [f"{r[k]}mA" for k in ("budget_5v_ma", "bus_5v_ma", "i24_fixed_ma", "i24_loaded_ma") if r.get(k)]
        if r["kind"] == "cpu":
            want.append(f"{r['di']}inputs/{r['do']}outputs")
            assert "MaximumnumberofPROFINETdevice8" in text(r["profinet_page"]), r
        assert all(w in t for w in want), (r["model"], [w for w in want if w not in t])


def test_st70_s71200g2_rows_are_printed_on_their_pages():
    """G6: every article, module current and CPU I/O count of st70_s71200g2.yaml is in the ST 70 text."""
    import pypdfium2 as pdfium
    from core.provenance import register
    pdf = pdfium.PdfDocument(str(ROOT / "sources" / register()["SIE-ST70-2026"]["file"]))
    text = lambda n: re.sub(r"\s+", "", pdf[n - 1].get_textpage().get_text_range().replace("‑", "-"))
    for r in rows("st70_s71200g2.yaml", ("article", "model", "kind")):
        t = text(r["page"])
        assert r["article"] in t and r["printed"] in t, r
        if r["kind"] == "cpu":
            spec = text(r["page"] + 2)
            assert f"{r['max_sm']}extensionmodules" in t, r
            assert f"Numberofdigitalinputs{r['di']};" in spec and f"Numberofdigitaloutputs{r['do']};" in spec, r
        else:
            want = [f"{r['bus_5v_ma']}mA"] + [f"{r[k]:g}mA" for k in ("lplus_typ_ma", "lplus_outputs_ma") if r.get(k)]
            assert all(w in t for w in want), (r["model"], want)


def test_st70_s71500_et200sp_and_cpu1513_rows_are_printed():
    """G6: articles, IO-device limits, IM data, DQ module currents and the CPU 1513 supply figures are in the PDFs."""
    import pypdfium2 as pdfium
    from core.provenance import register
    st = pdfium.PdfDocument(str(ROOT / "sources" / register()["SIE-ST70-2026"]["file"]))
    text = lambda pdf, n: re.sub(r"\s+", "", pdf[n - 1].get_textpage().get_text_range().replace("‑", "-"))
    for r in rows("st70_s71500_et200sp.yaml", ("article", "model", "kind")):
        assert r["article"] in text(st, r["page"]), r
        if r["kind"] == "cpu":
            assert f"NumberofconnectableIODevices,max.{r['profinet_max_devices']}" in text(st, r["spec_page"]), r
        if r["kind"] == "im":
            assert f"{r['current_ma']}mA" in text(st, r["spec_page"]) and "max.16323264" in text(st, r["spec_page"]), r
        if r.get("out_a_per_module"):
            assert "Currentpermodule,max.4A8A8A" in text(st, r["spec_page"]), r
    cpu = pdfium.PdfDocument(str(ROOT / "sources" / register()["SIE-CPU1513-MAN"]["file"]))
    for r in rows("s71500_cpu1513_power.yaml", ("item", "value")):
        assert re.sub(r"\s+", "", r["text"]) in text(cpu, r["page"]), r


def test_et200sp_module_manual_rows_are_printed():
    """G6: every row of the ET 200SP module power tables is printed on its page of the module's equipment manual."""
    import pypdfium2 as pdfium
    from core.provenance import register
    for name in ("et200sp_di16st_power.yaml", "et200sp_dq16st_power.yaml", "et200sp_aq4st_power.yaml"):
        d = load_sourced_table(data_file(name), ("item", "value"))
        pdf = pdfium.PdfDocument(str(ROOT / "sources" / register()[d["source"]["ref"]]["file"]))
        for r in d["rows"]:
            t = re.sub(r"\s+", "", pdf[r["page"] - 1].get_textpage().get_text_range())
            assert re.sub(r"\s+", "", r["text"].split(" (")[0])[:40] in t, (name, r)


def test_g2_cpu_power_and_ai4_rows_are_printed():
    """G6: S7-1200 G2 CPU budgets / output types (system manual) and the AI 4xU/I ST supply figures are in the PDFs."""
    import pypdfium2 as pdfium
    from core.provenance import register
    doc = lambda ref: pdfium.PdfDocument(str(ROOT / "sources" / register()[ref]["file"]))
    text = lambda pdf, n: re.sub(r"\s+", "", pdf[n - 1].get_textpage().get_text_range())
    g = doc("SIE-S71200G2-SYS")
    for r in rows("s71200g2_cpu_power.yaml", ("model",)):
        if r["article"] == "all":
            assert "40°CMax.specifications" in text(g, 361) and "60°CWithderating" in text(g, 361)
            continue
        t = text(g, r["page"]) + text(g, r["page"] + 1)
        assert r["article"] in t and f"{r['budget_5v_ma']}mAmax.(5VDC)" in t and f"sensorsupply{r['sensor_24v_ma']}mA" in t, r
        assert ("MOSFET(sourcing)" if r["do_type"] == "sourcing" else "Relay,drycontact") in text(g, r["do_page"]), r
    a = doc("SIE-ET200SP-AI4ST")
    for r in rows("et200sp_ai4st_power.yaml", ("item", "value")):
        assert re.sub(r"\s+", "", r["text"])[:35] in text(a, r["page"]), r
