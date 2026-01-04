from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import re

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def _find_text(root: ET.Element, path: str) -> str:
    """Find text by walking tag names ignoring namespaces. path like 'ide/nNF'."""
    parts = path.split("/")
    cur = root
    for part in parts:
        found = None
        for child in cur:
            if _strip_ns(child.tag) == part:
                found = child
                break
        if found is None:
            return ""
        cur = found
    return (cur.text or "").strip()

def parse_nfe_xml(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse a Brazilian NF-e XML (NFe/infNFe) and return header + item rows."""
    # NF-e can include many namespaces. We'll ignore them by stripping.
    root = ET.fromstring(xml_bytes)

    # Find infNFe
    infNFe = None
    for el in root.iter():
        if _strip_ns(el.tag) == "infNFe":
            infNFe = el
            break
    if infNFe is None:
        raise ValueError("XML não parece ser uma NF-e (infNFe não encontrado).")

    ide = None
    emit = None
    dest = None
    total = None
    for child in infNFe:
        name = _strip_ns(child.tag)
        if name == "ide": ide = child
        elif name == "emit": emit = child
        elif name == "dest": dest = child
        elif name == "total": total = child

    header = {
        "chave": infNFe.attrib.get("Id","").replace("NFe",""),
        "nNF": _find_text(infNFe, "ide/nNF"),
        "serie": _find_text(infNFe, "ide/serie"),
        "dhEmi": _find_text(infNFe, "ide/dhEmi") or _find_text(infNFe, "ide/dEmi"),
        "emit_xNome": _find_text(infNFe, "emit/xNome"),
        "emit_CNPJ": _find_text(infNFe, "emit/CNPJ") or _find_text(infNFe, "emit/CPF"),
        "dest_xNome": _find_text(infNFe, "dest/xNome"),
        "dest_CNPJ": _find_text(infNFe, "dest/CNPJ") or _find_text(infNFe, "dest/CPF"),
        "vNF": "",
    }
    # total/vNF
    header["vNF"] = _find_text(infNFe, "total/ICMSTot/vNF")

    items: List[Dict[str, Any]] = []
    for det in infNFe:
        if _strip_ns(det.tag) != "det":
            continue
        nItem = det.attrib.get("nItem","")
        prod = None
        imposto = None
        for c in det:
            n = _strip_ns(c.tag)
            if n == "prod": prod = c
            elif n == "imposto": imposto = c
        if prod is None:
            continue

        row = {
            "nItem": nItem,
            "cProd": _find_text(det, "prod/cProd"),
            "xProd": _find_text(det, "prod/xProd"),
            "NCM": _find_text(det, "prod/NCM"),
            "CFOP": _find_text(det, "prod/CFOP"),
            "uCom": _find_text(det, "prod/uCom"),
            "qCom": _find_text(det, "prod/qCom"),
            "vUnCom": _find_text(det, "prod/vUnCom"),
            "vProd": _find_text(det, "prod/vProd"),
            "CST_ICMS": "",
            "CSOSN": "",
            "orig": "",
            "pICMS": "",
            "vICMS": "",
        }

        # ICMS node can be ICMS00/ICMS10/ICMSSN102 etc
        icms = None
        if imposto is not None:
            for child in imposto:
                if _strip_ns(child.tag) == "ICMS":
                    icms = child
                    break
        if icms is not None:
            # first child inside ICMS is the modality node
            icms_mod = None
            for child in icms:
                icms_mod = child
                break
            if icms_mod is not None:
                row["orig"] = _find_text(icms_mod, "orig")
                row["CST_ICMS"] = _find_text(icms_mod, "CST")
                row["CSOSN"] = _find_text(icms_mod, "CSOSN")
                row["pICMS"] = _find_text(icms_mod, "pICMS")
                row["vICMS"] = _find_text(icms_mod, "vICMS")

        items.append(row)

    return {"header": header, "items": items}