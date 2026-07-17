#!/usr/bin/env python3
"""Descarrega a tabela completa do indicador INE 0014698 pela API oficial."""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

INDICATOR = "0014698"
LANG = "PT"
BASE_URL = "https://www.ine.pt/ine/json_indicador/pindica.jsp"
META_URL = "https://www.ine.pt/ine/json_indicador/pindicaMeta.jsp"
OUT_DIR = Path("output")


def get_json(url: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    request = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; ine-0014698-fetcher/1.0)",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        text = response.read().decode("utf-8-sig")
    return json.loads(text)


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("\xa0", "").replace(" ", "").replace(",", ".")
    if not text or text.upper() in {"NA", "N/A"}:
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
        raise RuntimeError("Formato inesperado: o primeiro elemento não é um objeto JSON")
    if root.get("Sucesso") is False:
        raise RuntimeError(f"A API reportou insucesso: {root}")

    dados = root.get("Dados")
    if not isinstance(dados, dict):
        raise RuntimeError("A resposta não contém o objeto 'Dados' esperado")

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
        "dim_6", "dim_6_t",
        "ind_string", "valor", "valor_numerico",
        "sinal_conv", "sinal_conv_desc",
    ]
    discovered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                discovered.append(key)
    return [c for c in preferred if c in seen] + [c for c in discovered if c not in preferred]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = ordered_columns(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def extract_title(metadata: Any) -> str | None:
    if isinstance(metadata, list) and metadata and isinstance(metadata[0], dict):
        obj = metadata[0]
    elif isinstance(metadata, dict):
        obj = metadata
    else:
        return None
    for key in ("Designacao", "designacao", "IndicadorDsg", "indicador_dsg"):
        value = obj.get(key)
        if value:
            return str(value)
    return None


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Dim1=T pede todos os períodos. As dimensões não indicadas são devolvidas
    # com todas as categorias disponíveis para o indicador.
    params = {"op": "2", "varcd": INDICATOR, "Dim1": "T", "lang": LANG}

    print("A descarregar dados do INE...", flush=True)
    payload = get_json(BASE_URL, params)
    (OUT_DIR / f"ine_{INDICATOR}_raw.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("A descarregar metadados do INE...", flush=True)
    metadata = get_json(META_URL, {"varcd": INDICATOR, "lang": LANG})
    (OUT_DIR / f"ine_{INDICATOR}_metadados.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = flatten_data(payload)
    if not rows:
        raise RuntimeError("A API respondeu sem observações")

    csv_path = OUT_DIR / f"ine_{INDICATOR}_tabela_completa.csv"
    write_csv(csv_path, rows)

    info = {
        "codigo_indicador": INDICATOR,
        "titulo": extract_title(metadata),
        "endpoint_dados": BASE_URL,
        "parametros": params,
        "endpoint_metadados": META_URL,
        "numero_observacoes": len(rows),
        "numero_colunas": len(ordered_columns(rows)),
        "colunas": ordered_columns(rows),
    }
    (OUT_DIR / f"ine_{INDICATOR}_info.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    script_path = Path(__file__)
    (OUT_DIR / script_path.name).write_text(
        script_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    print(
        f"Concluído: {len(rows)} observações e {len(ordered_columns(rows))} colunas.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERRO: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
