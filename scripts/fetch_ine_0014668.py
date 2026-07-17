#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

INDICATOR = "0014668"
LANG = "PT"
BASE_URL = "https://www.ine.pt/ine/json_indicador/pindica.jsp"
META_URL = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp"
OUT_DIR = Path("output")


def get_json(url: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ine-0014668-fetcher/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        text = resp.read().decode("utf-8-sig")
    return json.loads(text)


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    if text == "" or text.upper() == "NA":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def flatten_data(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Formato inesperado da API: {type(payload).__name__}")
    root = payload[0]
    if not isinstance(root, dict):
        raise RuntimeError("Formato inesperado: primeiro elemento não é objeto JSON")
    if root.get("Sucesso") is False:
        raise RuntimeError(f"A API reportou insucesso: {root}")
    dados = root.get("Dados")
    if not isinstance(dados, dict):
        raise RuntimeError("Resposta sem objeto 'Dados'")

    rows: list[dict[str, Any]] = []
    for period_code, observations in dados.items():
        if observations is None:
            continue
        if not isinstance(observations, list):
            observations = [observations]
        for obs in observations:
            row: dict[str, Any] = {"periodo_codigo_api": period_code}
            if isinstance(obs, dict):
                row.update(obs)
            else:
                row["observacao"] = obs
            if "valor" in row:
                row["valor_numerico"] = parse_number(row.get("valor"))
            rows.append(row)
    return rows


def ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "periodo_codigo_api",
        "dim_1", "dim_1_t",
        "geocod", "geodsg",
        "dim_2", "dim_2_t",
        "dim_3", "dim_3_t",
        "dim_4", "dim_4_t",
        "dim_5", "dim_5_t",
        "ind_string", "valor", "valor_numerico",
        "sinal_conv", "sinal_conv_desc",
    ]
    all_cols = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                all_cols.append(key)
    return [c for c in preferred if c in seen] + [c for c in all_cols if c not in preferred]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    cols = ordered_columns(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    params = {"op": "2", "varcd": INDICATOR, "Dim1": "T", "lang": LANG}

    print("Fetching INE data...", flush=True)
    payload = get_json(BASE_URL, params)
    (OUT_DIR / f"ine_{INDICATOR}_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("Fetching INE metadata...", flush=True)
    metadata = get_json(META_URL, {"varcd": INDICATOR, "lang": LANG})
    (OUT_DIR / f"ine_{INDICATOR}_metadados.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = flatten_data(payload)
    csv_path = OUT_DIR / f"ine_{INDICATOR}_tabela_completa.csv"
    write_csv(csv_path, rows)

    info = {
        "codigo_indicador": INDICATOR,
        "endpoint_dados": BASE_URL,
        "parametros": params,
        "endpoint_metadados": META_URL,
        "numero_observacoes": len(rows),
        "colunas": ordered_columns(rows),
    }
    (OUT_DIR / f"ine_{INDICATOR}_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Done: {len(rows)} observations", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
