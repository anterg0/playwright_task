import os
import sys
import argparse
import logging
import time
import json
from typing import Optional, Dict, Any, List

import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor, Json

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import impressum
from impressum import (
    fetch_and_process_impressum,
    extract_with_deepseek,
    normalize_url,
)


class CompanyStatus:
    PENDING = None
    OK = 0
    NO_IMPRESSUM_LINK_FOUND = 1
    PARSING_FAILED = 2
    ADDRESS_INCOMPLETE = 3
    ERROR = 4
    NO_WEBSITE = 5


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

POLL_DELAY = 1.0


def connect_db():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def get_companies_to_process(
    company_name: Optional[str] = None,
    limit: Optional[int] = None,
    status_filter: Optional[int] = None
) -> List[Dict[str, Any]]:
    db = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

    try:
        with db.cursor(cursor_factory=RealDictCursor) as cursor:
            if company_name:
                cursor.execute("""
                    SELECT id, company_name, language, country, postcode, city, street, house_no, web,
                           status, impressum_url, legal_name, postal_address, handelsregister,
                           vat_number, phone, email, responsible_person, raw_json,
                           created_at, updated_at
                    FROM companies
                    WHERE company_name = %s
                """, (company_name,))
            else:
                if status_filter is not None:
                    cursor.execute("""
                        SELECT id, company_name, language, country, postcode, city, street, house_no, web,
                               status, impressum_url, legal_name, postal_address, handelsregister,
                               vat_number, phone, email, responsible_person, raw_json,
                               created_at, updated_at
                        FROM companies
                        WHERE status = %s
                        ORDER BY id
                    """, (status_filter,))
                else:
                    cursor.execute("""
                        SELECT id, company_name, language, country, postcode, city, street, house_no, web,
                               status, impressum_url, legal_name, postal_address, handelsregister,
                               vat_number, phone, email, responsible_person, raw_json,
                               created_at, updated_at
                        FROM companies
                        WHERE status IS NULL OR status <> 0
                        ORDER BY id
                    """)

            rows = cursor.fetchall()
            return rows
    finally:
        db.close()


def update_company_status(company_id: int, updates: Dict[str, Any]):
    set_clauses = []
    values = []

    for key, value in updates.items():
        if value is not None:
            if isinstance(value, (dict, list)):
                value = Json(value)
            set_clauses.append(f"{key} = %s")
            values.append(value)

    if not set_clauses:
        return

    set_clauses.append("updated_at = NOW()")

    query = f"""
        UPDATE companies
        SET {', '.join(set_clauses)}
        WHERE id = %s
    """
    values.append(company_id)

    db = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )

    try:
        with db.cursor() as cursor:
            cursor.execute(query, values)
            db.commit()
    finally:
        db.close()


def process_company(company: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    company_id = company["id"]
    company_name = company["company_name"]
    web = company.get("web")

    logger.info(f"Processing company {company['id']}: {company_name}")

    web_url = web.strip() if web else ""
    if not web_url:
        logger.info(f"Company {company_name}: No website URL provided")
        return {"status": 5, "error": "No website URL provided"}

    web_url = impressum.normalize_url(web_url)
    logger.info(f"Processing {company_name} with URL: {web_url}")

    try:
        result = impressum.fetch_and_process_impressum(company_name, web_url)

        if result.get("error"):
            error_msg = result["error"]
            status = result.get("status")

            if status == 5:
                return {"status": 5, "error": "No website URL"}
            elif status == 1:
                return {"status": 1, "error": "No Impressum/Imprint link found"}
            elif status == 4:
                return {"status": 4, "error": f"Fetch failed: {result['error']}"}
            else:
                return {"status": 4, "error": f"Fetch failed: {result['error']}"}

        impressum_url = result["impressum_url"]
        optimized_text = result.get("optimized_text", "")
        stats = result.get("stats", {})

        logger.info(f"Impressum found: {result['impressum_url']}")
        logger.info(f"Text optimization: {result.get('stats', {}).get('original_chars', 0)} -> {result.get('stats', {}).get('optimized_chars', 0)} chars ({result.get('stats', {}).get('reduction_pct', 0):.1f}% reduction)")

        if dry_run:
            logger.info("=== DRY RUN - DeepSeek Prompt ===")
            logger.info(f"System prompt length: {len(impressum.SYSTEM_PROMPT)} chars")
            logger.info(f"User prompt (optimized text) length: {len(optimized_text)} chars")
            logger.info(f"Estimated input tokens: {len(optimized_text) // 4}")
            logger.info("=== Optimized text preview (first 500 chars) ===")
            logger.info(optimized_text[:500])
            logger.info("... (truncated)")
            logger.info("=== End DRY RUN ===")
            return {
                "status": 0,
                "impressum_url": impressum_url,
                "optimized_text_preview": optimized_text[:500],
                "stats": stats,
                "dry_run": True
            }

        extracted = impressum.extract_with_deepseek(optimized_text)

        legal_name = extracted.get("company_name")
        postal_address_obj = extracted.get("postal_address", {})
        handelsregister = extracted.get("handelsregister")
        vat_number = extracted.get("vat_number")
        phone = extracted.get("phone")
        email = extracted.get("email")
        responsible_person = extracted.get("responsible_person")

        address_parts = []
        addr = postal_address_obj or {}
        if addr.get("street"):
            addr_str = addr["street"]
            if addr.get("house_no"):
                addr_str += f" {addr['house_no']}"
            address_parts.append(addr_str)
        if addr.get("postcode"):
            address_parts.append(addr["postcode"])
        if addr.get("city"):
            address_parts.append(addr["city"])
        if addr.get("country"):
            address_parts.append(addr["country"])
        postal_address = ", ".join(filter(None, address_parts)) if address_parts else None

        raw_json = {
            "company_name": extracted.get("company_name"),
            "postal_address": postal_address_obj,
            "handelsregister": extracted.get("handelsregister"),
            "vat_number": extracted.get("vat_number"),
            "phone": extracted.get("phone"),
            "email": extracted.get("email"),
            "responsible_person": extracted.get("responsible_person"),
        }

        has_any_field = any(v for v in [
            extracted.get("company_name"),
            extracted.get("handelsregister"),
            extracted.get("vat_number"),
            extracted.get("phone"),
            extracted.get("email"),
            extracted.get("responsible_person"),
        ] if v)

        if not has_any_field:
            status = 2
            logger.warning(f"Company {company_name}: No fields detected (PARSING_FAILED)")
        else:
            addr = postal_address_obj or {}
            address_complete = all([
                addr.get("postcode"),
                addr.get("city"),
                addr.get("street"),
                addr.get("house_no"),
            ])

            if not address_complete:
                status = 3
                logger.info(f"Company {company_name}: Address incomplete (ADDRESS_INCOMPLETE)")
            else:
                status = 0
                logger.info(f"Company {company_name}: Enrichment OK")

        return {
            "status": status,
            "impressum_url": impressum_url,
            "legal_name": legal_name,
            "postal_address": postal_address,
            "handelsregister": handelsregister,
            "vat_number": vat_number,
            "phone": phone,
            "email": email,
            "responsible_person": responsible_person,
            "raw_json": extracted,
        }

    except Exception as e:
        logger.error(f"DeepSeek extraction failed for {company_name}: {e}")
        return {"status": 4, "error": f"DeepSeek extraction failed: {e}"}

    except Exception as e:
        logger.error(f"Unexpected error processing {company_name}: {e}")
        return {"status": 4, "error": f"Processing error: {e}"}


def process_companies(
    company_name: Optional[str] = None,
    limit: Optional[int] = None,
    status_filter: Optional[int] = None,
    dry_run: bool = False,
    mock_company_url: Optional[str] = None
):
    if dry_run and mock_company_url:
        companies = [{
            "id": 0,
            "company_name": "Mock Company",
            "web": mock_company_url,
            "status": None,
            "impressum_url": None,
            "legal_name": None,
            "postal_address": None,
            "handelsregister": None,
            "vat_number": None,
            "phone": None,
            "email": None,
            "responsible_person": None,
            "raw_json": None,
            "created_at": None,
            "updated_at": None,
        }]
        logger.info(f"DRY RUN with mock company: {mock_company_url}")
    else:
        companies = get_companies_to_process(
            company_name=company_name,
            limit=limit,
            status_filter=status_filter
        )

    if not companies:
        logger.info("No companies to process")
        return

    if limit:
        companies = companies[:limit]

    logger.info(f"Found {len(companies)} companies to process")

    processed = 0
    succeeded = 0
    failed = 0

    for company in companies:
        try:
            result = process_company(company, dry_run=dry_run)
            status = result.get("status")

            if not dry_run:
                updates = {}
                if "status" in result:
                    updates["status"] = result["status"]
                if "impressum_url" in result:
                    updates["impressum_url"] = result.get("impressum_url")
                if "legal_name" in result:
                    updates["legal_name"] = result.get("legal_name")
                if "postal_address" in result:
                    updates["postal_address"] = result.get("postal_address")
                if "handelsregister" in result:
                    updates["handelsregister"] = result.get("handelsregister")
                if "vat_number" in result:
                    updates["vat_number"] = result.get("vat_number")
                if "phone" in result:
                    updates["phone"] = result.get("phone")
                if "email" in result:
                    updates["email"] = result.get("email")
                if "responsible_person" in result:
                    updates["responsible_person"] = result.get("responsible_person")
                if "raw_json" in result:
                    updates["raw_json"] = result.get("raw_json")

                if updates:
                    update_company_status(company["id"], updates)

            if result.get("status") == 0:
                succeeded += 1
            else:
                failed += 1

            processed += 1
            logger.info(f"Processed {company['company_name']}: status={result.get('status')}")

            if not dry_run:
                time.sleep(1)

        except Exception as e:
            logger.error(f"Error processing {company['company_name']}: {e}")
            failed += 1
            processed += 1
            continue

    logger.info(f"Done. Processed: {processed}, Succeeded: {succeeded}, Failed: {failed}")


def main():
    parser = argparse.ArgumentParser(description="Enrich company data with Impressum/Imprint extraction")
    parser.add_argument("--company", type=str, help="Process only this company by name")
    parser.add_argument("--limit", type=int, help="Process at most N rows")
    parser.add_argument("--status", type=int, help="Process only rows with this status (default: pending rows)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be sent to DeepSeek without calling API")
    parser.add_argument("--mock-company", type=str, help="Use mock company data for testing (provide web URL)")

    args = parser.parse_args()

    if not args.dry_run and not os.environ.get("DEEPSEEK_API_KEY"):
        logger.error("DEEPSEEK_API_KEY environment variable not set")
        sys.exit(1)

    logger.info("Starting company enrichment")
    logger.info(f"Args: company={args.company}, limit={args.limit}, status={args.status}, dry_run={args.dry_run}, mock_company={args.mock_company}")

    try:
        process_companies(
            company_name=args.company,
            limit=args.limit,
            status_filter=args.status,
            dry_run=args.dry_run,
            mock_company_url=args.mock_company
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import time
    import os
    main()