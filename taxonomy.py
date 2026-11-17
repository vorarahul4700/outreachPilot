"""City, category and tech IDs for companies.

Filters match on companies.city_id / companies.category_id / company_techs.tech_id,
never on text. This module turns the free text that scrapers, admins and the AI
write (city, search_keyword, profile tech_stack) into those IDs:

- register(): a save hook, so every writer keeps the IDs current without changes.
- backfill(): fills rows saved before the IDs existed (runs at startup, cheap when done).

Canonical rules:
- city: the part after the last comma, title-cased ("Thaltej, Ahmedabad" -> "Ahmedabad").
- category: seo_engine.normalize_keyword_to_category() of normalized_keyword, else search_keyword.
  Its industry is get_category_domain_code(); unmapped categories belong to IT, as before.
- tech: seo_engine.tech_to_slug() of each tech_stack entry.
"""
import threading

from sqlalchemy import event, inspect, text

from db import Company, CompanyProfile, engine

_cache: dict[str, dict[str, int]] = {"cities": {}, "categories": {}, "techs": {}, "industries": {}}
_lock = threading.Lock()


# --- canonical names -------------------------------------------------------

def city_name(raw: str | None) -> str:
    part = (raw or "").split(",")[-1]
    return " ".join(part.split()).title()


def raw_keyword(normalized_keyword: str | None, search_keyword: str | None) -> str:
    return (normalized_keyword or "").strip() or (search_keyword or "").strip()


def category_of(raw_kw: str) -> tuple[str, str, str]:
    """(slug, display name, industry code) for a raw scrape keyword."""
    import seo_engine
    name = seo_engine.normalize_keyword_to_category(raw_kw)
    code = seo_engine.get_category_domain_code(name)
    return seo_engine.tech_to_slug(name), name, ("it" if code == "all" else code)


def tech_of(raw_tech: str) -> tuple[str, str]:
    import seo_engine
    slug = seo_engine.tech_to_slug(raw_tech)
    return slug, seo_engine.CURATED_ACRONYM_MAP.get(slug) or " ".join(raw_tech.split())


# --- ID lookups (create on first sight) ------------------------------------

def _upsert(conn, table: str, slug: str, name: str, industry_id: int | None = None) -> int:
    cached = _cache[table].get(slug)
    if cached:
        return cached
    if table == "categories":
        conn.execute(text("INSERT INTO categories (slug, name, industry_id, is_hidden) VALUES (:s, :n, :i, FALSE) "
                          "ON CONFLICT (slug) DO NOTHING"), {"s": slug, "n": name, "i": industry_id})
    else:
        conn.execute(text(f"INSERT INTO {table} (slug, name) VALUES (:s, :n) ON CONFLICT (slug) DO NOTHING"),
                     {"s": slug, "n": name})
    row_id = conn.execute(text(f"SELECT id FROM {table} WHERE slug = :s"), {"s": slug}).scalar()
    with _lock:
        _cache[table][slug] = row_id
    return row_id


def industry_id(conn, code: str) -> int:
    if not _cache["industries"]:
        import seo_engine
        for d in seo_engine.INDUSTRY_DOMAINS:
            conn.execute(text("INSERT INTO industries (code, name, slug) VALUES (:c, :n, :s) ON CONFLICT (code) DO NOTHING"),
                         {"c": d["code"], "n": d["name"], "s": d["slug"]})
        with _lock:
            _cache["industries"].update({r[0]: r[1] for r in conn.execute(text("SELECT code, id FROM industries"))})
    return _cache["industries"].get(code) or _cache["industries"]["it"]


def city_id(conn, raw_city: str | None) -> int | None:
    name = city_name(raw_city)
    if not name:
        return None
    import seo_engine
    return _upsert(conn, "cities", seo_engine.city_to_slug(name), name)


def category_id(conn, raw_kw: str) -> int | None:
    if not raw_kw:
        return None
    slug, name, code = category_of(raw_kw)
    return _upsert(conn, "categories", slug, name, industry_id(conn, code)) if slug else None


def tech_id(conn, raw_tech: str) -> int | None:
    slug, name = tech_of(raw_tech)
    return _upsert(conn, "techs", slug, name[:120]) if slug else None


# --- save hook -------------------------------------------------------------

def _changed(obj, attr: str) -> bool:
    return inspect(obj).attrs[attr].history.has_changes()


def _before_flush(session, flush_context, instances):
    companies = [o for o in list(session.new) + list(session.dirty) if isinstance(o, Company)]
    if not companies:
        return
    # Taxonomy rows commit on their own connection, so parallel workers never race on them.
    with engine.begin() as conn:
        for c in companies:
            is_new = c in session.new
            if is_new or _changed(c, "city"):
                c.city_id = city_id(conn, c.city)
            if is_new or _changed(c, "search_keyword") or _changed(c, "normalized_keyword"):
                c.category_id = category_id(conn, raw_keyword(c.normalized_keyword, c.search_keyword))


def _after_flush(session, flush_context):
    profiles = [
        p for p in list(session.new) + list(session.dirty)
        if isinstance(p, CompanyProfile) and p.company_id and (p in session.new or _changed(p, "tech_stack"))
    ]
    if not profiles:
        return
    sess_conn = session.connection()
    with engine.begin() as conn:
        for p in profiles:
            ids = {tech_id(conn, t) for t in (p.tech_stack or []) if isinstance(t, str) and t.strip()}
            ids.discard(None)
            sess_conn.execute(text("DELETE FROM company_techs WHERE company_id = :c"), {"c": p.company_id})
            if ids:
                sess_conn.execute(text("INSERT INTO company_techs (company_id, tech_id) VALUES (:c, :t) ON CONFLICT DO NOTHING"),
                                  [{"c": p.company_id, "t": t} for t in ids])


def register(session_factory) -> None:
    event.listen(session_factory, "before_flush", _before_flush)
    event.listen(session_factory, "after_flush", _after_flush)


# --- backfill --------------------------------------------------------------

KW_SQL = "COALESCE(NULLIF(trim(normalized_keyword), ''), trim(search_keyword), '')"


def backfill() -> None:
    """Fill IDs for rows saved before the save hook existed. Postgres only; a no-op once done."""
    if engine.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL statement_timeout = '300s'"))
        industry_id(conn, "it")  # seeds industries

        raw_cities = [r[0] for r in conn.execute(text(
            "SELECT DISTINCT city FROM companies WHERE city_id IS NULL AND city IS NOT NULL AND trim(city) <> ''"))]
        for raw in raw_cities:
            cid = city_id(conn, raw)
            if cid:
                conn.execute(text("UPDATE companies SET city_id = :i WHERE city_id IS NULL AND city = :r"), {"i": cid, "r": raw})

        raw_kws = [r[0] for r in conn.execute(text(
            f"SELECT DISTINCT {KW_SQL} FROM companies WHERE category_id IS NULL AND {KW_SQL} <> ''"))]
        for raw in raw_kws:
            cat = category_id(conn, raw)
            if cat:
                conn.execute(text(f"UPDATE companies SET category_id = :i WHERE category_id IS NULL AND {KW_SQL} = :r"),
                             {"i": cat, "r": raw})

        if not conn.execute(text("SELECT EXISTS (SELECT 1 FROM company_techs)")).scalar():
            raw_techs = [r[0] for r in conn.execute(text(
                "SELECT DISTINCT trim(t) FROM company_profiles, jsonb_array_elements_text(tech_stack) t "
                "WHERE jsonb_typeof(tech_stack) = 'array' AND trim(t) <> ''"))]
            conn.execute(text("CREATE TEMP TABLE tmp_tech_map (raw TEXT, tech_id INT) ON COMMIT DROP"))
            pairs = [{"r": raw, "t": tech_id(conn, raw)} for raw in raw_techs]
            pairs = [p for p in pairs if p["t"]]
            if pairs:
                conn.execute(text("INSERT INTO tmp_tech_map (raw, tech_id) VALUES (:r, :t)"), pairs)
                conn.execute(text(
                    "INSERT INTO company_techs (company_id, tech_id) "
                    "SELECT DISTINCT cp.company_id, m.tech_id FROM company_profiles cp "
                    "CROSS JOIN LATERAL jsonb_array_elements_text(cp.tech_stack) t "
                    "JOIN tmp_tech_map m ON m.raw = trim(t) "
                    "WHERE jsonb_typeof(cp.tech_stack) = 'array' ON CONFLICT DO NOTHING"))

        if raw_cities or raw_kws:
            print(f"[Taxonomy] Backfilled {len(raw_cities)} city values and {len(raw_kws)} keywords to IDs.")
