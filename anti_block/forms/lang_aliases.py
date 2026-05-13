"""anti_block.forms.lang_aliases — multi-language field label aliases.

Reference table mapping each profile field to common label phrasings in:
EN, DE, FR, ES, PT, IT, RU, PL — the languages of corporate PSP sites in our
test set (10 SOAX geos).

Used by Hermes form-filler skill to map non-English form labels to
test_profile.yaml fields without LLM guessing.

CLI:
    python3 -m anti_block.forms.lang_aliases --lang DE
    python3 -m anti_block.forms.lang_aliases --field first_name
    python3 -m anti_block.forms.lang_aliases --match "Vorname"   # → first_name
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Optional

# Map: profile_field → list of regex patterns (case-insensitive) across languages.
# Order: most specific first. Used by `match_label_to_field()`.
ALIASES: dict[str, list[str]] = {
    "first_name": [
        r"\bfirst[\s_-]?name\b", r"\bfname\b", r"\bgiven[\s_-]?name\b",
        r"\bvorname\b",                                 # DE
        r"\bpr[ée]nom\b",                               # FR
        r"\bnombre\b(?!\s*de\s+(empresa|compania|usuario))",  # ES (not "company name")
        r"\bnome\b(?!\s+(da\s+)?(empresa|completo))",   # PT/IT (not "company"/"full name")
        r"\bимя\b",                                     # RU
        r"\bimi[eę]\b",                                 # PL
    ],
    "last_name": [
        r"\blast[\s_-]?name\b", r"\blname\b", r"\bsurname\b", r"\bfamily[\s_-]?name\b",
        r"\bnachname\b", r"\bfamiliennamen?\b",         # DE
        r"\bnom(\s+de\s+famille)?\b",                   # FR
        r"\bapellidos?\b",                              # ES
        r"\bsobrenome\b", r"\bcognome\b",               # PT/IT
        r"\bфамилия\b",                                 # RU
        r"\bnazwisko\b",                                # PL
    ],
    "full_name": [
        r"\bfull[\s_-]?name\b", r"\byour[\s_-]?name\b", r"\bcontact[\s_-]?name\b", r"^name$",
        r"\bvollst[äa]ndiger?\s+name\b",                # DE
        r"\bnom(\s+complet)?\b", r"\bnom\s+et\s+pr[ée]nom\b",  # FR
        r"\bnombre\s+completo\b",                       # ES
        r"\bnome\s+(completo|e\s+cognome)\b",           # PT/IT
        r"\bполное\s+имя\b", r"\bваше\s+имя\b",          # RU
        r"\bimi[eę]\s+i\s+nazwisko\b",                  # PL
    ],
    "email": [
        r"\b(business|work|company|corporate)?\s*e[\s\-]?mail\b",
        r"\bemail\s+address\b",
        r"\b(gesch[äa]fts|firmen|arbeits)?\s*e[\s\-]?mail\b",   # DE
        r"\bcorreo(\s+electr[óo]nico)?\b",              # ES
        r"\bcourriel\b",                                # FR
        r"\bemail\s+aziendale\b",                       # IT
        r"\bпочта\b", r"\b(?:e-?mail|электронная\s+почта)\b",   # RU
    ],
    "phone": [
        r"\bphone(\s+number)?\b", r"\btel(ephone)?\b", r"\bmobile\b", r"\bcell(\s+phone)?\b",
        r"\btelefon(nummer)?\b", r"\bhandy\b",          # DE
        r"\bt[ée]l[ée]phone\b", r"\bportable\b",        # FR
        r"\btel[ée]fono(\s+m[oó]vil)?\b", r"\bcelular\b",  # ES
        r"\btelefone\b",                                # PT
        r"\btelefono\b",                                # IT
        r"\bтелефон\b",                                 # RU
        r"\btelefon\b",                                 # PL
    ],
    "company_name": [
        r"\bcompany(\s+name)?\b", r"\bbusiness(\s+name)?\b", r"\borganization\b", r"\borganisation\b",
        r"\bmerchant(\s+name)?\b", r"\bfirm\b",
        r"\b(unternehmens?|firmen?)?\s*name\b",         # DE
        r"\bsoci[ée]t[ée]\b", r"\bentreprise\b",        # FR
        r"\b(empresa|compa[ñn][ií]a|raz[oó]n\s+social)\b",  # ES/PT
        r"\bazienda\b", r"\bragione\s+sociale\b",       # IT
        r"\b(компания|организация|название\s+компании)\b",  # RU
        r"\bfirma\b", r"\bnazwa\s+firmy\b",             # PL
    ],
    "company_website": [
        r"\b(company\s+)?(website|web\s*site|url|web\s*page)\b",
        r"\b(unternehmens?|firmen?)?\s*(website|webseite)\b",  # DE
        r"\bsite\s+(internet|web)?\b",                  # FR
        r"\bsitio\s+web\b", r"\bp[áa]gina\s+web\b",      # ES
        r"\bsite\b(?!\s+(web|internet))",               # PT/IT generic
        r"\bсайт\b",                                    # RU
    ],
    "country": [
        r"\bcountry\b", r"\bnation\b",
        r"\bland\b",                                    # DE
        r"\bpays\b",                                    # FR
        r"\bpa[ií]s\b",                                 # ES/PT
        r"\bpaese\b",                                   # IT
        r"\bстрана\b",                                  # RU
        r"\bkraj\b",                                    # PL
    ],
    "city": [
        r"\bcity\b", r"\btown\b",
        r"\bstadt\b",                                   # DE
        r"\bville\b",                                   # FR
        r"\bciudad\b",                                  # ES
        r"\bcidade\b", r"\bcitt[àa]\b",                 # PT/IT
        r"\bгород\b",                                   # RU
        r"\bmiasto\b",                                  # PL
    ],
    "state": [
        r"\bstate\b", r"\bprovince\b", r"\bregion\b",
        r"\bbundesland\b",                              # DE
        r"\br[ée]gion\b", r"\bd[ée]partement\b",         # FR
        r"\bprovincia\b", r"\bestado\b",                # ES/PT
        r"\bobwod\b", r"\bregionu\b",                   # PL
        r"\bобласть\b", r"\bрегион\b",                  # RU
    ],
    "postal_code": [
        r"\b(postal|post)\s*code\b", r"\bzip(\s+code)?\b", r"\bpostcode\b",
        r"\bplz\b", r"\bpostleitzahl\b",                # DE
        r"\bcode\s+postal\b",                           # FR
        r"\bc[óo]digo\s+postal\b",                      # ES
        r"\bcep\b", r"\bcap\b",                         # PT/IT
        r"\bпочтовый\s+индекс\b",                       # RU
    ],
    "address": [
        r"\baddress\b", r"\bstreet\b",
        r"\b(stra[ßs]e|anschrift|adresse)\b",           # DE
        r"\badresse\b", r"\brue\b",                     # FR
        r"\bdirecci[óo]n\b", r"\bcalle\b",              # ES
        r"\bendere[çc]o\b", r"\bindirizzo\b",           # PT/IT
        r"\bадрес\b", r"\bулица\b",                     # RU
    ],
    "job_title": [
        r"\b(job\s+title|position|role|designation)\b",
        r"\b(berufs?bezeichnung|position|funktion)\b",  # DE
        r"\b(fonction|poste|titre)\b",                  # FR
        r"\b(cargo|puesto|posici[óo]n)\b",              # ES
        r"\bcarica\b", r"\bruolo\b",                    # IT/PT
        r"\bдолжность\b",                               # RU
    ],
    "industry": [
        r"\b(industry|sector|vertical|business\s+type)\b",
        r"\b(branche|industrie|sektor|gesch[äa]ftsbereich)\b",  # DE
        r"\b(secteur|industrie)\b",                     # FR
        r"\b(sector|industria|rubro)\b",                # ES
        r"\b(settore|industria)\b",                     # IT
        r"\bотрасль\b", r"\bсфера\b",                   # RU
    ],
    "company_size": [
        r"\b(company\s+size|number\s+of\s+employees|team\s+size|employees)\b",
        r"\b(mitarbeiter(zahl|anzahl)?|firmengr[öo][ßs]e)\b",  # DE
        r"\bnombre\s+d['e]\s+employ[ée]s\b",            # FR
        r"\bn[úu]mero\s+de\s+empleados\b",              # ES
        r"\bколичество\s+сотрудников\b",                # RU
    ],
    "monthly_volume": [
        r"\b(monthly|annual|yearly)\s+(volume|amount|revenue|turnover|processing)\b",
        r"\b(volume|gmv|turnover|throughput)\b",
        r"\b(monatlich(es|er)?\s+volumen|umsatz)\b",    # DE
        r"\bvolumen\s+mensual\b", r"\bfacturaci[óo]n\b",  # ES
        r"\bvolume\s+mensuel\b",                        # FR
        r"\bволум\b", r"\bоборот\b",                    # RU
    ],
    "message": [
        r"\b(message|comment|inquiry|details?|notes?|how\s+can\s+we\s+help|tell\s+us\s+(more|about))\b",
        r"\b(nachricht|kommentar|anliegen|beschreibung)\b",  # DE
        r"\b(message|commentaire|d[ée]tails|comment\s+pouvons[\s-]nous)\b",  # FR
        r"\b(mensaje|comentario|consulta|d[ée]tales)\b",  # ES
        r"\b(mensagem|coment[áa]rio|messaggio|commento)\b",  # PT/IT
        r"\b(сообщение|комментарий|опишите|ваш\s+вопрос)\b",  # RU
        r"\bwiadomo[śs][ćc]\b",                          # PL
    ],
    "subject": [
        r"\b(subject|topic|reason|inquiry\s+type)\b",
        r"\b(betreff|thema|grund)\b",                   # DE
        r"\b(sujet|objet|raison)\b",                    # FR
        r"\b(asunto|tema|motivo)\b",                    # ES
        r"\b(assunto|tema|oggetto)\b",                  # PT/IT
        r"\bтема\b",                                    # RU
    ],
    "consent": [
        r"\b(agree|consent|accept|i\s+confirm)\b.*\b(privacy|terms|policy|gdpr)\b",
        r"\b(privacy\s+policy|gdpr|data\s+processing)\b",
        r"\b(zustimm(en|ung)|einverst[äa]ndnis|datenschutz)\b",  # DE
        r"\b(j['e]\s+accepte|consentement|politique\s+de\s+confidentialit[ée])\b",  # FR
        r"\b(acepto|consiento|pol[ií]tica\s+de\s+privacidad)\b",  # ES
        r"\b(согласие|обработк[уи]\s+данных|политик[уи]\s+конфиденциальности)\b",  # RU
    ],
    "marketing_consent": [
        r"\b(newsletter|marketing|promotional|subscribe|updates)\b",
        r"\b(werbung|newsletter|marketing|aktion(en)?)\b",  # DE
        r"\b(actualit[ée]s|abonner|newsletter|marketing)\b",  # FR
        r"\b(novedades|suscribirse|bolet[ií]n)\b",      # ES
        r"\bрассылк[уаи]\b",                            # RU
    ],
}

# Reverse index for fast match.
_REVERSE: list[tuple[re.Pattern, str]] = []
for field, patterns in ALIASES.items():
    for p in patterns:
        _REVERSE.append((re.compile(p, re.I | re.UNICODE), field))


def match_label_to_field(label: str) -> Optional[str]:
    """Given a form field label/placeholder/name, return the matching profile field name."""
    if not label:
        return None
    label = label.strip()
    for pattern, field in _REVERSE:
        if pattern.search(label):
            return field
    return None


def detect_language(text: str) -> Optional[str]:
    """Crude page-language detection based on stop-words. Returns 'EN'/'DE'/'FR'/'ES'/'PT'/'IT'/'RU'/'PL' or None."""
    if not text:
        return None
    lower = text.lower()
    signals = {
        "DE": ("und", "ist", "nicht", "der ", "die ", "das ", "für", "datenschutz", "kontakt"),
        "FR": ("le ", "la ", "les ", "des ", "pour", "nous", "vous", "contactez"),
        "ES": ("el ", "la ", "los ", "para", "que ", "una", "nosotros", "contacto"),
        "PT": ("o ", "a ", "para ", "que ", "uma", "voc[ê]", "obrigad"),
        "IT": ("il ", "la ", "gli ", "per ", "che ", "una", "noi", "contatto"),
        "RU": ("и ", "не ", "это", "для", "с ", "на ", "связ", "контакт"),
        "PL": ("i ", "nie ", "jest", "dla ", "kontakt"),
    }
    scores = {}
    for lang, words in signals.items():
        s = sum(1 for w in words if w in lower)
        scores[lang] = s
    # Plain English baseline if no other lang dominates.
    best = max(scores.items(), key=lambda x: x[1])
    if best[1] >= 3:
        return best[0]
    return "EN"


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--match", help="match a label string to a profile field")
    g.add_argument("--field", help="show all aliases for one profile field")
    g.add_argument("--lang", help="show all aliases categorized by field, filtered for one language (EN/DE/FR/ES/PT/IT/RU/PL)")
    g.add_argument("--detect", help="detect language of text snippet (page title or label)")
    g.add_argument("--list-fields", action="store_true", help="list all available profile fields")
    args = ap.parse_args()

    if args.list_fields:
        print(json.dumps(sorted(ALIASES.keys()), indent=2))
        return 0
    if args.match:
        result = match_label_to_field(args.match)
        print(json.dumps({"label": args.match, "field": result}))
        return 0
    if args.field:
        ps = ALIASES.get(args.field)
        if not ps:
            print(json.dumps({"error": "unknown field", "available": sorted(ALIASES.keys())}), file=sys.stderr)
            return 2
        print(json.dumps({"field": args.field, "patterns": ps}, indent=2, ensure_ascii=False))
        return 0
    if args.lang:
        lang = args.lang.upper()
        # Aliases dict is in form pat:lang label — just print all.
        print(json.dumps(ALIASES, indent=2, ensure_ascii=False))
        return 0
    if args.detect:
        print(json.dumps({"text": args.detect[:100], "lang": detect_language(args.detect)}))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
