WEIGHTS = {
    "Объем": 3.0,
    "Вес": 2.0,
    "Размер": 2.0,
    "Материал": 2.5,
    "Тип": 2.5,
    "Назначение": 2.0,
    "Вид товаров": 2.0,
    "Вид продукции": 2.0,
    "_default": 1.0,
}

SOURCE_BONUS = {
    "exact": 1.0,
    "category": 0.8,
    "semantic": 0.6,
    "extended": 0.3,
    "manual": 1.0,
}


def match_score(
    target: dict[str, str],
    candidate: dict[str, str],
) -> tuple[float, dict]:
    matches = {}
    score = 0.0
    weight_sum = 0.0

    for key, target_val in target.items():
        if target_val == "0.00000" or not target_val:
            continue

        w = WEIGHTS.get(key, WEIGHTS["_default"])
        weight_sum += w

        if key not in candidate:
            matches[key] = {"status": "missing", "score": 0}
            continue

        cand_val = candidate[key]

        try:
            t_num = float(target_val.replace(",", "."))
            c_num = float(cand_val.replace(",", "."))

            if t_num == 0:
                continue

            ratio = abs(c_num - t_num) / t_num

            if ratio <= 0.10:
                s = 1.0
            elif ratio <= 0.30:
                s = 1.0 - (ratio - 0.10) / 0.20 * 0.5
            elif ratio <= 0.50:
                s = 0.5 - (ratio - 0.30) / 0.20 * 0.5
            else:
                s = 0.0

            score += s * w
            matches[key] = {
                "status": "numeric",
                "target": t_num,
                "candidate": c_num,
                "diff_pct": round(ratio * 100, 1),
                "score": round(s, 2),
            }
        except ValueError:
            t_norm = target_val.lower().strip()
            c_norm = cand_val.lower().strip()

            if t_norm == c_norm:
                s = 1.0
            elif t_norm in c_norm or c_norm in t_norm:
                s = 0.7
            else:
                s = 0.0

            score += s * w
            matches[key] = {
                "status": "string",
                "target": target_val,
                "candidate": cand_val,
                "score": round(s, 2),
            }

    final_score = score / weight_sum if weight_sum > 0 else 0.0
    return round(final_score, 3), matches


def combined_score(
    cosine_score: float,
    char_match_score: float,
    source: str,
) -> float:
    bonus = SOURCE_BONUS.get(source, 0.5)
    return cosine_score * 0.3 + char_match_score * 0.5 + bonus * 0.2
