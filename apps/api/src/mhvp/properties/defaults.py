"""Tenant defaults for M4: catalogues and allocation key template (annex A.2, A.3, 6.2).

Only the lists named in the master prompt; tenants extend them. Adding is idempotent.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mhvp.properties.models import AllocationKeyTemplate, AllocationKind, CatalogEntry

# Section 6.2 (meter) and annex A.3 (Zählerarten).
METER_TYPES: tuple[tuple[str, str], ...] = (
    ("gas", "Gas"),
    ("heating", "Heizung"),
    ("cold_water", "Kaltwasser"),
    ("hot_water", "Warmwasser"),
    ("electricity", "Strom"),
    ("water_commercial", "Wasser gewerblich"),
    ("water_non_commercial", "Wasser nicht gewerblich"),
    ("heat_meter", "Wärmemengenzähler"),
    ("heat_cost_allocator", "Heizkostenverteiler"),
    ("tenant_change_without_meter", "Mieterwechsel ohne Zähler"),
)
# Section 6.2 (service_provider_relation.contract_type_id).
PROVIDER_CONTRACT_TYPES: tuple[tuple[str, str], ...] = (
    ("caretaker", "Hausmeister"),
    ("cleaning", "Reinigung"),
    ("winter_service", "Winterdienst"),
    ("heating_maintenance", "Wartung Heizung"),
    ("elevator", "Aufzug"),
    ("insurance", "Versicherung"),
    ("metering_service", "Messdienst"),
    ("energy", "Energie"),
)
# Section 6.2 (property_contact.category).
PROPERTY_CONTACT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("caretaker", "Hausmeister"),
    ("board", "Beirat"),
    ("emergency", "Notdienst"),
    ("utility", "Versorger"),
)
# Section 6.3 (contract_payment.payment_type_id) and annex A.3 (Zahlungsarten).
PAYMENT_TYPES: tuple[tuple[str, str], ...] = (
    ("rent", "Miete"),
    ("operating_cost_advance", "Betriebskosten-Vorauszahlung"),
    ("heating_cost_advance", "Heizkosten-Vorauszahlung"),
    ("garage", "Garagenmiete"),
    ("parking", "Stellplatzmiete"),
    ("rent_reduction", "Mietminderung"),
    ("hoa_fee", "Hausgeld"),
    ("reserve", "Erhaltungsrücklage"),
    ("special_levy", "Sonderumlage"),
    ("other", "Sonstige"),
)
REDUCTION_PAYMENT_TYPES = frozenset({"rent_reduction"})
CATALOGS: dict[str, tuple[tuple[str, str], ...]] = {
    "payment_type": PAYMENT_TYPES,
    "meter_type": METER_TYPES,
    "provider_contract_type": PROVIDER_CONTRACT_TYPES,
    "property_contact_category": PROPERTY_CONTACT_CATEGORIES,
}

S, C, F, FS = (
    AllocationKind.STATIC,
    AllocationKind.CONSUMPTION,
    AllocationKind.FIXED_AMOUNT,
    AllocationKind.FIXED_SHARE,
)
# Annex A.2 standard list. Names are reference terms, not a statement on allocability (A.2, 7.2).
ALLOCATION_KEYS: tuple[tuple[str, str, str, AllocationKind, str | None], ...] = (
    ("WFL", "Wohnfläche", "m²", S, None),
    ("HZF", "Heizfläche", "m²", S, None),
    ("WWF", "Warmwasserfläche", "m²", S, None),
    ("UR", "Umbauter Raum", "cbm", S, None),
    ("MEA", "Miteigentumsanteil", "Anzahl", S, None),
    ("EINH", "Anzahl Einheit", "Einh.", S, None),
    ("PERS", "Personen", "Personen", S, None),
    ("KTV", "Kabel-TV", "Einh.", S, None),
    ("MUELL", "Müllentsorgung", "m²", S, None),
    ("AUFZ", "Aufzugsnutzung", "m²", S, None),
    ("FEST", "Festumlage", "EUR", F, None),
    ("EXT_WASSER", "Extern berechnete Wasser- und sonstige Kosten", "EUR", F, None),
    ("EXT_HEIZ", "Extern berechnete Heizkosten", "EUR", F, None),
    ("V_GAS", "Verbrauch Gas", "kWh", C, "gas"),
    ("V_HEIZ", "Verbrauch Heizung", "kWh", C, "heating"),
    ("V_KW", "Verbrauch Kaltwasser", "m³", C, "cold_water"),
    ("V_WW", "Verbrauch Warmwasser", "m³", C, "hot_water"),
    ("V_STROM", "Verbrauch Strom", "kWh", C, "electricity"),
    ("V_WG", "Verbrauch Wasser gewerblich", "m³", C, "water_commercial"),
    ("V_WNG", "Verbrauch Wasser nicht gewerblich", "m³", C, "water_non_commercial"),
    ("V_MW", "Mieterwechsel ohne Zähler", "Anzahl", C, "tenant_change_without_meter"),
)
_ = FS  # fixed_share keys are created per property when a resolution defines them


async def ensure_tenant_defaults(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    for catalog, entries in CATALOGS.items():
        existing = set(
            (
                await session.scalars(
                    select(CatalogEntry.code).where(CatalogEntry.catalog == catalog)
                )
            ).all()
        )
        for order, (code, label) in enumerate(entries):
            if code not in existing:
                session.add(
                    CatalogEntry(
                        tenant_id=tenant_id,
                        catalog=catalog,
                        code=code,
                        label=label,
                        sort_order=order,
                    )
                )
    existing_keys = set((await session.scalars(select(AllocationKeyTemplate.code))).all())
    for order, (code, name, uom, kind, meter) in enumerate(ALLOCATION_KEYS):
        if code not in existing_keys:
            session.add(
                AllocationKeyTemplate(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    unit_of_measure=uom,
                    kind=kind,
                    meter_type_code=meter,
                    sort_order=order,
                )
            )
    await session.flush()
