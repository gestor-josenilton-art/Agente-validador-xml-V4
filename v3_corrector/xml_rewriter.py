from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Dict
import re

def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag

def _digits(s: str) -> str:
    return re.sub(r"\D+","", str(s or ""))

def rewrite_nfe_xml(xml_bytes: bytes, changes_by_nitem: Dict[str, Dict[str,str]]) -> bytes:
    """Apply changes to NF-e XML by det@nItem.
    changes_by_nitem: { '1': {'NCM':'12345678', 'CFOP':'5102', 'CST':'060', 'CSOSN':'102'} }
    Only modifies present nodes.
    """
    root = ET.fromstring(xml_bytes)
    # find infNFe
    infNFe=None
    for el in root.iter():
        if _strip_ns(el.tag)=="infNFe":
            infNFe=el; break
    if infNFe is None:
        return xml_bytes

    for det in list(infNFe):
        if _strip_ns(det.tag)!="det":
            continue
        nItem = det.attrib.get("nItem","")
        if nItem not in changes_by_nitem:
            continue
        changes = changes_by_nitem[nItem]

        # prod
        prod=None
        imposto=None
        for c in det:
            t=_strip_ns(c.tag)
            if t=="prod": prod=c
            elif t=="imposto": imposto=c
        if prod is not None:
            for node in list(prod):
                t=_strip_ns(node.tag)
                if t=="NCM" and "NCM" in changes:
                    node.text = _digits(changes["NCM"]).zfill(8)[:8]
                if t=="CFOP" and "CFOP" in changes:
                    node.text = _digits(changes["CFOP"]).zfill(4)[:4]

        # ICMS CST/CSOSN
        if imposto is not None and ("CST" in changes or "CSOSN" in changes):
            icms=None
            for child in imposto:
                if _strip_ns(child.tag)=="ICMS":
                    icms=child; break
            if icms is not None:
                icms_mod=None
                for child in icms:
                    icms_mod=child; break
                if icms_mod is not None:
                    for node in list(icms_mod):
                        t=_strip_ns(node.tag)
                        if t=="CST" and "CST" in changes:
                            node.text = _digits(changes["CST"]).zfill(2)[-2:] if len(_digits(changes["CST"]))<=2 else _digits(changes["CST"]).zfill(3)[:3]
                        if t=="CSOSN" and "CSOSN" in changes:
                            node.text = _digits(changes["CSOSN"]).zfill(3)[:3]

    # Serialize keeping encoding utf-8
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
