#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

INDICATOR = "0014698"
LANG = "PT"
BASE_URL = "https://www.ine.pt/ine/json_indicador/pindica.jsp"
META_URL = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp"
OUT_DIR = Path("output")


def get_json(url: str, params: dict[str, str], attempts: int = 4) -> Any:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                full_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; INE-table-fetcher/1.0)",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8-sig"))
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Falha ao obter {full_url}: {last_error}")


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text or text.upper() in {"NA", "N/A", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def flatten_data(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise RuntimeError("Formato inesperado da resposta da API do INE")
    root = payload[0]
    if root.get("Sucesso") is False:
        raise RuntimeError(f"A API reportou insucesso: {root}")
    dados = root.get("Dados")
    if not isinstance(dados, dict):
        raise RuntimeError("A resposta não contém o objeto 'Dados'")

    rows: list[dict[str, Any]] = []
    for period_code, observations in dados.items():
        if observations is None:
            continue
        if not isinstance(observations, list):
            observations = [observations]
        for observation in observations:
            row: dict[str, Any] = {"periodo_codigo_api": period_code}
            if isinstance(observation, dict):
                row.update(observation)
            else:
                row["observacao"] = observation
            if "valor" in row:
                row["valor_numerico"] = parse_number(row.get("valor"))
            rows.append(row)
    return root, rows


def ordered_columns(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "periodo_codigo_api",
        "dim_1", "dim_1_t",
        "geocod", "geodsg",
        "dim_2", "dim_2_t",
        "dim_3", "dim_3_t",
        "dim_4", "dim_4_t",
        "dim_5", "dim_5_t",
        "dim_6", "dim_6_t",
        "ind_string", "valor", "valor_numerico",
        "sinal_conv", "sinal_conv_desc",
    ]
    seen: list[str] = []
    seen_set: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen_set:
                seen_set.add(key)
                seen.append(key)
    return [c for c in preferred if c in seen_set] + [c for c in seen if c not in preferred]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> list[str]:
    columns = ordered_columns(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return columns


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data_params = {"op": "2", "varcd": INDICATOR, "Dim1": "T", "lang": LANG}
    meta_params = {"varcd": INDICATOR, "lang": LANG}

    print("A obter a tabela completa do INE...", flush=True)
    payload = get_json(BASE_URL, data_params)
    root, rows = flatten_data(payload)

    raw_path = OUT_DIR / f"ine_{INDICATOR}_raw.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("A obter metadados...", flush=True)
    metadata = get_json(META_URL, meta_params)
    meta_path = OUT_DIR / f"ine_{INDICATOR}_metadados.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = OUT_DIR / f"ine_{INDICATOR}_tabela_completa.csv"
    columns = write_csv(csv_path, rows)

    info = {
        "codigo_indicador": INDICATOR,
        "designacao_indicador": root.get("IndicadorDsg"),
        "ultima_atualizacao": root.get("DataUltimoAtualizacao"),
        "fonte": root.get("Fonte"),
        "endpoint_dados": BASE_URL,
        "parametros_dados": data_params,
        "endpoint_metadados": META_URL,
        "parametros_metadados": meta_params,
        "numero_observacoes": len(rows),
        "numero_colunas": len(columns),
        "colunas": columns,
    }
    (OUT_DIR / f"ine_{INDICATOR}_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Concluído: {len(rows)} observações e {len(columns)} colunas", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
