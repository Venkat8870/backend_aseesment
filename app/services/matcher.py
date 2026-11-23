def match_events(rows: list[dict], active_codes: dict[str, str]) -> list[dict]:
    wanted = {code.strip().upper(): sev for code, sev in active_codes.items()}
    matched = []
    for row in rows:
        code = row["event_code"].strip().upper()
        if code in wanted:
            matched.append({**row, "event_code": code, "severity": wanted[code]})
    return matched