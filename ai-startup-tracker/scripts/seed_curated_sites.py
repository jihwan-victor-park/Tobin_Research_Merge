"""
Bulk-register a curated list of well-known accelerator / VC / university
portfolio pages so the orchestrator can scrape them on its next run.

Each entry is a tuple of (url, category). Domain is derived via
canonicalize_domain(). Existing rows are skipped (HealthMonitor.register_site
no-ops on duplicates). Newly inserted rows have:
  - difficulty='hard' (agentic engine — the URLs were not picked because they
    have a hardcoded scraper)
  - worker_state='pending' (first scrape decides)
  - category set from the curated bucket
  - scraper_name='curated:<category>' so we can audit the batch

Run:
    python scripts/seed_curated_sites.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db.connection import session_scope
from backend.db.models import SiteHealth
from backend.orchestrator.health import HealthMonitor
from backend.utils.domain import canonicalize_domain

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seed_curated")


# (url, category) — keep URLs deep-linked to portfolio/companies pages where
# possible; the agentic engine handles the rest.
CURATED: list[tuple[str, str]] = [
    # ── Tier-1 US VC portfolio pages ────────────────────────────────
    ("https://a16z.com/portfolio/",                                "vc_portfolio"),
    ("https://www.sequoiacap.com/our-companies/",                  "vc_portfolio"),
    ("https://www.bvp.com/portfolio",                              "vc_portfolio"),
    ("https://foundersfund.com/the-portfolio/",                    "vc_portfolio"),
    ("https://www.indexventures.com/companies/",                   "vc_portfolio"),
    ("https://www.gv.com/portfolio/",                              "vc_portfolio"),
    ("https://www.accel.com/companies",                            "vc_portfolio"),
    ("https://www.benchmark.com/companies/",                       "vc_portfolio"),
    ("https://greylock.com/portfolio/",                            "vc_portfolio"),
    ("https://www.kleinerperkins.com/portfolio/",                  "vc_portfolio"),
    ("https://www.nea.com/portfolio",                              "vc_portfolio"),
    ("https://www.generalcatalyst.com/portfolio",                  "vc_portfolio"),
    ("https://foundationcap.com/portfolio/",                       "vc_portfolio"),
    ("https://www.mayfield.com/companies/",                        "vc_portfolio"),
    ("https://m12.vc/portfolio/",                                  "vc_portfolio"),
    ("https://www.redpoint.com/portfolio/",                        "vc_portfolio"),
    ("https://www.nvp.com/portfolio/",                             "vc_portfolio"),
    ("https://www.battery.com/our-companies/",                     "vc_portfolio"),
    ("https://www.ivp.com/portfolio/",                             "vc_portfolio"),
    ("https://www.usv.com/portfolio/",                             "vc_portfolio"),
    ("https://firstround.com/companies/",                          "vc_portfolio"),
    ("https://www.forerunnerventures.com/portfolio",               "vc_portfolio"),
    ("https://www.thrivecap.com/companies",                        "vc_portfolio"),
    ("https://www.coatue.com/portfolio",                           "vc_portfolio"),
    ("https://www.tigerglobal.com/portfolio",                      "vc_portfolio"),
    ("https://www.spark.capital/portfolio",                        "vc_portfolio"),
    ("https://www.emcap.com/portfolio/",                           "vc_portfolio"),
    ("https://www.madrona.com/portfolio/",                         "vc_portfolio"),
    ("https://pearvc.com/portfolio/",                              "vc_portfolio"),
    ("https://www.signalfire.com/portfolio",                       "vc_portfolio"),
    ("https://www.cowboy.vc/companies",                            "vc_portfolio"),
    ("https://www.floodgate.com/founders",                         "vc_portfolio"),
    ("https://www.meritechcapital.com/portfolio",                  "vc_portfolio"),
    ("https://www.baincapitalventures.com/portfolio/",             "vc_portfolio"),
    ("https://lsvp.com/companies/",                                "vc_portfolio"),
    ("https://www.crv.com/portfolio/",                             "vc_portfolio"),
    ("https://www.felicis.com/portfolio",                          "vc_portfolio"),
    ("https://www.shasta.vc/portfolio",                            "vc_portfolio"),
    ("https://www.contrarycap.com/portfolio",                      "vc_portfolio"),
    ("https://www.scalevp.com/portfolio",                          "vc_portfolio"),
    ("https://sapphireventures.com/portfolio/",                    "vc_portfolio"),
    ("https://www.insightpartners.com/portfolio/",                 "vc_portfolio"),
    ("https://nfx.com/portfolio",                                  "vc_portfolio"),
    ("https://www.true.vc/portfolio",                              "vc_portfolio"),
    ("https://www.canaan.com/portfolio",                           "vc_portfolio"),
    ("https://menlovc.com/portfolio/",                             "vc_portfolio"),
    ("https://www.foundrygroup.com/portfolio/",                    "vc_portfolio"),
    ("https://www.bondcap.com/portfolio",                          "vc_portfolio"),
    ("https://www.iconiqcapital.com/growth/portfolio",             "vc_portfolio"),
    ("https://www.altimetercapital.com/portfolio/",                "vc_portfolio"),
    ("https://gradient.com/portfolio/",                            "vc_portfolio"),
    ("https://www.craftventures.com/portfolio",                    "vc_portfolio"),
    ("https://initialized.com/companies",                          "vc_portfolio"),
    ("https://www.kholsaventures.com/portfolio",                   "vc_portfolio"),
    ("https://www.menloventures.com/portfolio/",                   "vc_portfolio"),
    ("https://www.ggvc.com/portfolio/",                            "vc_portfolio"),
    ("https://www.matrixpartners.com/companies/",                  "vc_portfolio"),
    ("https://www.upfront.com/portfolio/",                         "vc_portfolio"),
    ("https://defy.vc/companies/",                                 "vc_portfolio"),

    # ── AI-focused funds ────────────────────────────────────────────
    ("https://aigrant.com/",                                       "vc_portfolio"),
    ("https://www.conviction.com/portfolio",                       "vc_portfolio"),
    ("https://www.radical.vc/portfolio",                           "vc_portfolio"),
    ("https://airstreet.com/portfolio",                            "vc_portfolio"),
    ("https://www.pi.capital/portfolio",                           "vc_portfolio"),
    ("https://compound.vc/portfolio",                              "vc_portfolio"),

    # ── Accelerators ─────────────────────────────────────────────────
    ("https://500.co/startups",                                    "accelerator"),
    ("https://masschallenge.org/programs/",                        "accelerator"),
    ("https://www.plugandplaytechcenter.com/our-investments/",     "accelerator"),
    ("https://creativedestructionlab.com/companies/",              "accelerator"),
    ("https://www.beondeck.com/founders",                          "accelerator"),
    ("https://launchhouse.com/portfolio",                          "accelerator"),
    ("https://www.alphalab.org/portfolio",                         "accelerator"),
    ("https://www.boomtownaccelerator.com/portfolio",              "accelerator"),
    ("https://www.brandery.org/companies/",                        "accelerator"),
    ("https://launch.co/companies",                                "accelerator"),
    ("https://www.dmzaccelerator.com/companies/",                  "accelerator"),
    ("https://www.thefoundry.com/portfolio",                       "accelerator"),
    ("https://www.fasttrackmalmo.com/portfolio",                   "accelerator"),
    ("https://hubspotventures.com/portfolio/",                     "accelerator"),
    ("https://www.50partners.fr/our-startups",                     "accelerator"),
    ("https://www.zinclaunch.com/portfolio",                       "accelerator"),
    ("https://www.iccelerate.com/portfolio",                       "accelerator"),
    ("https://startupwiseguys.com/portfolio/",                     "accelerator"),
    ("https://www.kickstartfund.com/portfolio/",                   "accelerator"),
    ("https://newchip.com/portfolio",                              "accelerator"),
    ("https://www.expa.com/companies",                             "accelerator"),
    ("https://www.bethnalgreenventures.com/ventures/",             "accelerator"),
    ("https://www.numa.co/companies",                              "accelerator"),
    ("https://www.startupreserve.com/portfolio",                   "accelerator"),

    # ── US University programs ──────────────────────────────────────
    ("https://entrepreneurship.mit.edu/companies/",                "university_incubator"),
    ("https://trust.mit.edu/our-startups",                         "university_incubator"),
    ("https://sandbox.mit.edu/teams",                              "university_incubator"),
    ("https://venturelab.yale.edu/programs",                       "university_incubator"),
    ("https://tsai.yale.edu/people/ventures",                      "university_incubator"),
    ("https://entrepreneurship.upenn.edu/about/our-startups/",     "university_incubator"),
    ("https://venturelab.upenn.edu/our-startups",                  "university_incubator"),
    ("https://thegarage.northwestern.edu/companies/",              "university_incubator"),
    ("https://entrepreneurship.duke.edu/our-startups/",            "university_incubator"),
    ("https://eship.cornell.edu/student-startups/",                "university_incubator"),
    ("https://entrepreneurship.dartmouth.edu/portfolio",           "university_incubator"),
    ("https://www.blackstonelaunchpad.org/companies",              "university_incubator"),
    ("https://launchpad.utexas.edu/portfolio",                     "university_incubator"),
    ("https://create-x.gatech.edu/startups",                       "university_incubator"),
    ("https://innovation.umd.edu/portfolio/",                      "university_incubator"),
    ("https://startup.ucla.edu/companies",                         "university_incubator"),
    ("https://entrepreneurship.usc.edu/portfolio/",                "university_incubator"),
    ("https://www.cdtm.com/portfolio/",                            "university_incubator"),
    ("https://chicagobooth.edu/research/polsky/programs",          "university_incubator"),
    ("https://polsky.uchicago.edu/programs-and-events/",           "university_incubator"),
    ("https://gw-ileg.org/portfolio",                              "university_incubator"),
    ("https://innovation.gatech.edu/portfolio",                    "university_incubator"),
    ("https://innovation.washington.edu/about/portfolio/",         "university_incubator"),
    ("https://entrepreneurship.umich.edu/students/",               "university_incubator"),
    ("https://nyuentrepreneur.org/companies/",                     "university_incubator"),
    ("https://entrepreneurship.virginia.edu/companies",            "university_incubator"),
    ("https://www.kentstateaccelerator.com/portfolio",             "university_incubator"),
    ("https://nuvention.northwestern.edu/teams/",                  "university_incubator"),
    ("https://eship.gatech.edu/companies",                         "university_incubator"),
    ("https://innovation.cornell.edu/companies",                   "university_incubator"),
    ("https://gsb.stanford.edu/insights/center-entrepreneurial-studies/portfolio", "university_incubator"),
    ("https://startuplab.stanford.edu/portfolio",                  "university_incubator"),

    # ── Government / public programs ────────────────────────────────
    ("https://seedfund.nsf.gov/awardees/",                         "government_program"),
    ("https://www.sbir.gov/sbirsearch/firm/all",                   "government_program"),
    ("https://www.darpa.mil/program/small-business-programs",      "government_program"),
    ("https://www.sba.gov/funding-programs/investment-capital",    "government_program"),
    ("https://www.energy.gov/eere/technology-to-market/portfolio", "government_program"),
    ("https://arpa-e.energy.gov/technologies/projects",            "government_program"),

    # ── Discovery / aggregators ─────────────────────────────────────
    ("https://www.f6s.com/programs",                               "discovery_aggregator"),
    ("https://www.startupgrind.com/startups/",                     "discovery_aggregator"),
    ("https://dealroom.co/companies",                              "discovery_aggregator"),
    ("https://www.cbinsights.com/research-unicorn-companies",      "discovery_aggregator"),
    ("https://pitchbook.com/news/articles/the-complete-list-of-unicorn-companies", "discovery_aggregator"),
    ("https://www.producthunt.com/topics/artificial-intelligence", "discovery_aggregator"),
    ("https://theresanaiforthat.com/",                             "discovery_aggregator"),
    ("https://www.futurepedia.io/",                                "discovery_aggregator"),

    # ── International accelerators / programs ───────────────────────
    ("https://www.foundercentric.com/portfolio",                   "accelerator"),
    ("https://primer.kr/portfolio",                                "accelerator"),
    ("https://blueprint.kr/companies",                             "accelerator"),
    ("https://www.kstartup.go.kr",                                 "government_program"),
    ("https://www.k-startup.go.kr",                                "government_program"),
    ("https://startup.google.com/programs/accelerator/",           "accelerator"),
    ("https://nextai.com/companies/",                              "accelerator"),
    ("https://www.startuplisboa.com/companies",                    "accelerator"),
    ("https://www.ihub.co.ke/portfolio",                           "accelerator"),

    # ════════════════════════════════════════════════════════════════════════
    # EXTENDED LIST v2 — added later for broader coverage
    # Goal: deeply categorized 400+ sources of US/EU/Asia portfolios.
    # ════════════════════════════════════════════════════════════════════════

    # ── More Tier-1/2 US VCs ────────────────────────────────────────────
    ("https://www.lightspeedvp.com/portfolio/",                    "vc_portfolio"),
    ("https://www.khoslaventures.com/portfolio",                   "vc_portfolio"),
    ("https://www.norwestvp.com/companies/",                       "vc_portfolio"),
    ("https://www.tcv.com/portfolio/",                             "vc_portfolio"),
    ("https://www.dragoneer.com/companies",                        "vc_portfolio"),
    ("https://andreessen.com/portfolio",                           "vc_portfolio"),
    ("https://eclipse.vc/portfolio/",                              "vc_portfolio"),
    ("https://8vc.com/companies/",                                 "vc_portfolio"),
    ("https://www.lererhippeau.com/portfolio",                     "vc_portfolio"),
    ("https://bowerycapital.com/portfolio/",                       "vc_portfolio"),
    ("https://www.muckercapital.com/portfolio",                    "vc_portfolio"),
    ("https://www.costanoa.vc/portfolio",                          "vc_portfolio"),
    ("https://www.dcm.com/portfolio/",                             "vc_portfolio"),
    ("https://obvious.com/portfolio",                              "vc_portfolio"),
    ("https://socialcapital.com/companies",                        "vc_portfolio"),
    ("https://andreessen-horowitz.com/portfolio",                  "vc_portfolio"),
    ("https://www.benchmark.com/companies",                        "vc_portfolio"),
    ("https://www.thrive.cm/portfolio",                            "vc_portfolio"),
    ("https://hmlt.com/portfolio",                                 "vc_portfolio"),
    ("https://www.lookoutvc.com/portfolio",                        "vc_portfolio"),
    ("https://www.cota-capital.com/portfolio/",                    "vc_portfolio"),
    ("https://www.boxgroup.com/companies",                         "vc_portfolio"),
    ("https://kindredventures.com/portfolio/",                     "vc_portfolio"),
    ("https://hawksridge.com/portfolio",                           "vc_portfolio"),
    ("https://citi-ventures.com/portfolio/",                       "vc_portfolio"),
    ("https://www.northzone.com/portfolio/",                       "vc_portfolio"),
    ("https://www.gradientventures.com/portfolio",                 "vc_portfolio"),
    ("https://www.workbench.vc/portfolio",                         "vc_portfolio"),
    ("https://www.sozocap.com/companies",                          "vc_portfolio"),

    # ── AI-native funds (super high signal) ─────────────────────────────
    ("https://www.menloventures.com/sectors/ai/",                  "vc_portfolio"),
    ("https://www.gradient.com/portfolio",                         "vc_portfolio"),
    ("https://greycroft.com/portfolio/",                           "vc_portfolio"),
    ("https://essence.vc/portfolio",                               "vc_portfolio"),
    ("https://innovationendeavors.com/portfolio/",                 "vc_portfolio"),
    ("https://newtheoryvc.com/portfolio/",                         "vc_portfolio"),
    ("https://amplifypartners.com/portfolio/",                     "vc_portfolio"),
    ("https://luxcapital.com/companies/",                          "vc_portfolio"),
    ("https://www.dcvc.com/companies/",                            "vc_portfolio"),
    ("https://www.glasswing.vc/our-portfolio",                     "vc_portfolio"),
    ("https://basisset.vc/portfolio/",                             "vc_portfolio"),
    ("https://primary.vc/portfolio",                               "vc_portfolio"),
    ("https://leadedge.com/portfolio/",                            "vc_portfolio"),
    ("https://www.scout-vc.com/portfolio",                         "vc_portfolio"),
    ("https://www.sandhillangels.com/portfolio",                   "vc_portfolio"),
    ("https://gigafund.com/companies/",                            "vc_portfolio"),
    ("https://emergencecapital.com/portfolio/",                    "vc_portfolio"),
    ("https://www.zettavp.com/portfolio",                          "vc_portfolio"),
    ("https://www.workbench.vc/companies",                         "vc_portfolio"),
    ("https://www.uphonest.com/portfolio",                         "vc_portfolio"),
    ("https://southparkcommons.com/companies",                     "vc_portfolio"),

    # ── Climate / DeepTech / Bio / FinTech specialists ──────────────────
    ("https://www.lowercarboncapital.com/portfolio",               "vc_portfolio"),
    ("https://www.energizecapital.com/portfolio",                  "vc_portfolio"),
    ("https://www.bevc.com/portfolio",                             "vc_portfolio"),
    ("https://www.pradaria.com/portfolio",                         "vc_portfolio"),
    ("https://www.thirdsphere.com/portfolio",                      "vc_portfolio"),
    ("https://www.union-square-ventures.com/portfolio",            "vc_portfolio"),
    ("https://www.nuventures.com/portfolio",                       "vc_portfolio"),
    ("https://www.flagshippioneering.com/companies",               "vc_portfolio"),
    ("https://archvp.com/portfolio/",                              "vc_portfolio"),
    ("https://www.polarispartners.com/portfolio/",                 "vc_portfolio"),
    ("https://www.thirdrock.com/companies/",                       "vc_portfolio"),
    ("https://breyer.com/portfolio/",                              "vc_portfolio"),
    ("https://www.section32.com/portfolio/",                       "vc_portfolio"),
    ("https://generalcatalyst.com/health-assurance/",              "vc_portfolio"),
    ("https://www.qedinvestors.com/portfolio",                     "vc_portfolio"),
    ("https://www.ribbitcapital.com/portfolio/",                   "vc_portfolio"),
    ("https://www.anthemis.com/portfolio/",                        "vc_portfolio"),
    ("https://www.financialventureslab.com/portfolio",             "vc_portfolio"),
    ("https://www.commerce-ventures.com/portfolio",                "vc_portfolio"),

    # ── Crypto / Web3 funds (often back AI infra too) ───────────────────
    ("https://a16zcrypto.com/portfolio/",                          "vc_portfolio"),
    ("https://www.paradigm.xyz/portfolio",                         "vc_portfolio"),
    ("https://multicoin.capital/portfolio/",                       "vc_portfolio"),
    ("https://placeholder.vc/companies",                           "vc_portfolio"),
    ("https://1confirmation.com/portfolio",                        "vc_portfolio"),
    ("https://variant.fund/portfolio/",                            "vc_portfolio"),
    ("https://drago.capital/portfolio",                            "vc_portfolio"),
    ("https://hackvc.com/portfolio/",                              "vc_portfolio"),

    # ── European VCs ────────────────────────────────────────────────────
    ("https://www.atomico.com/portfolio",                          "vc_portfolio"),
    ("https://eqtventures.com/companies/",                         "vc_portfolio"),
    ("https://www.balderton.com/portfolio/",                       "vc_portfolio"),
    ("https://localglobe.vc/portfolio/",                           "vc_portfolio"),
    ("https://speedinvest.com/portfolio/",                         "vc_portfolio"),
    ("https://www.lakestar.com/portfolio/",                        "vc_portfolio"),
    ("https://www.cherry.vc/portfolio",                            "vc_portfolio"),
    ("https://www.dnvgroup.com/portfolio",                         "vc_portfolio"),
    ("https://www.holtzbrinckventures.com/portfolio/",             "vc_portfolio"),
    ("https://www.frst.capital/portfolio",                         "vc_portfolio"),
    ("https://elaiacap.com/portfolio/",                            "vc_portfolio"),
    ("https://www.pointnine.com/portfolio",                        "vc_portfolio"),
    ("https://www.connectventures.co/portfolio",                   "vc_portfolio"),
    ("https://www.partechpartners.com/portfolio/",                 "vc_portfolio"),
    ("https://www.kinnevik.com/our-companies/",                    "vc_portfolio"),
    ("https://www.brent-hoberman.com/firstminute-portfolio",       "vc_portfolio"),
    ("https://www.kompasvc.com/portfolio",                         "vc_portfolio"),
    ("https://earlybird.com/portfolio/",                           "vc_portfolio"),
    ("https://www.nordicninjavc.com/portfolio",                    "vc_portfolio"),
    ("https://creandum.com/companies/",                            "vc_portfolio"),

    # ── Asian VCs ───────────────────────────────────────────────────────
    ("https://www.softbank.com/en/about/portfolio.html",           "vc_portfolio"),
    ("https://www.gobi.vc/portfolio",                              "vc_portfolio"),
    ("https://hashed.com/portfolio",                               "vc_portfolio"),
    ("https://kap.kr/portfolio",                                   "vc_portfolio"),
    ("https://altos.vc/portfolio",                                 "vc_portfolio"),
    ("https://www.kakaoventures.com/portfolio",                    "vc_portfolio"),
    ("https://www.smilegate.com/portfolio",                        "vc_portfolio"),
    ("https://www.naverd2.com/portfolio",                          "vc_portfolio"),
    ("https://www.mirae-asset.com/portfolio",                      "vc_portfolio"),
    ("https://gsr.vc/portfolio",                                   "vc_portfolio"),
    ("https://www.gobiventures.com/portfolio",                     "vc_portfolio"),
    ("https://chaivc.com/portfolio",                               "vc_portfolio"),
    ("https://www.matrixpartners.in/portfolio/",                   "vc_portfolio"),
    ("https://www.nexusvp.com/portfolio/",                         "vc_portfolio"),
    ("https://www.peakxv.com/portfolio/",                          "vc_portfolio"),
    ("https://accel.com/people/portfolio",                         "vc_portfolio"),
    ("https://www.elevation.cap/portfolio",                        "vc_portfolio"),
    ("https://www.lightboxvc.com/portfolio",                       "vc_portfolio"),

    # ── More accelerators ─────────────────────────────────────────────
    ("https://www.ai2incubator.com/companies",                     "accelerator"),
    ("https://pioneer.app/companies",                              "accelerator"),
    ("https://www.foundersinc.com/portfolio",                      "accelerator"),
    ("https://www.dayoneventures.com/portfolio",                   "accelerator"),
    ("https://southparkcommons.com/portfolio",                     "accelerator"),
    ("https://oncedeck.com/companies",                             "accelerator"),
    ("https://www.oxfordseedfund.com/portfolio",                   "accelerator"),
    ("https://www.cambridgeseedfund.com/portfolio",                "accelerator"),
    ("https://www.disney.com/accelerator",                         "accelerator"),
    ("https://www.disneyaccelerator.com/portfolio",                "accelerator"),
    ("https://www.creativedestructionlab.com/companies/",          "accelerator"),
    ("https://startupbootcamp.org/portfolio/",                     "accelerator"),
    ("https://www.tampabaywave.org/portfolio",                     "accelerator"),
    ("https://1871.com/companies/",                                "accelerator"),
    ("https://www.capitalinnovators.com/portfolio",                "accelerator"),
    ("https://www.matterchicago.com/portfolio",                    "accelerator"),
    ("https://galvanize.com/portfolio",                            "accelerator"),
    ("https://www.flatironschool.com/companies",                   "accelerator"),
    ("https://hax.co/portfolio/",                                  "accelerator"),
    ("https://www.lemnos.vc/portfolio/",                           "accelerator"),
    ("https://bolt.io/portfolio",                                  "accelerator"),
    ("https://www.indiebio.co/companies/",                         "accelerator"),
    ("https://www.petri.bio/portfolio",                            "accelerator"),
    ("https://www.activate.org/innovators",                        "accelerator"),
    ("https://greentownlabs.com/companies/",                       "accelerator"),
    ("https://thirdderivative.org/innovators/",                    "accelerator"),
    ("https://climate-kic.org/startups/",                          "accelerator"),
    ("https://elemental.org/innovation-portfolio/",                "accelerator"),
    ("https://www.preferredbynature.org/programs",                 "accelerator"),
    ("https://www.urban-x.com/companies/",                         "accelerator"),
    ("https://newlab.com/members/",                                "accelerator"),
    ("https://venturesforamerica.org/portfolio",                   "accelerator"),
    ("https://www.foundationcap.com/portfolio",                    "accelerator"),
    ("https://www.afore.com/portfolio",                            "accelerator"),
    ("https://www.entrepreneurfirst.org.uk/companies",             "accelerator"),
    ("https://www.entrepreneurfirst.com/companies",                "accelerator"),
    ("https://www.amaesgroup.com/companies",                       "accelerator"),
    ("https://www.greatpoint.com/portfolio",                       "accelerator"),
    ("https://www.greenrubinoinc.com/portfolio",                   "accelerator"),
    ("https://www.nexusgrowth.com/portfolio",                      "accelerator"),
    ("https://www.zaffire.com/portfolio",                          "accelerator"),

    # ── Corporate accelerators (often AI-focused) ────────────────────
    ("https://startups.microsoft.com/en-us/founders-hub/companies/", "accelerator"),
    ("https://startup.google.com/programs/accelerator/",           "accelerator"),
    ("https://aws.amazon.com/startups/portfolio",                  "accelerator"),
    ("https://nvidia.com/inception",                               "accelerator"),
    ("https://nvidiainceptioneco.com/companies",                   "accelerator"),
    ("https://www.salesforce.com/company/ventures/portfolio/",     "accelerator"),
    ("https://oracle.com/startup/portfolio/",                      "accelerator"),
    ("https://startups.intel.com/portfolio",                       "accelerator"),
    ("https://www.qualcomm.com/ventures/portfolio",                "accelerator"),
    ("https://stripe.com/atlas/companies",                         "accelerator"),
    ("https://shopify.engineering/startup-program/portfolio",      "accelerator"),
    ("https://www.spacex.com/seed",                                "accelerator"),
    ("https://www.amazon.com/alexa-fund/portfolio",                "accelerator"),
    ("https://www.cloudflare.com/launchpad/",                      "accelerator"),
    ("https://www.databricks.com/company/ventures",                "accelerator"),
    ("https://snowflake.com/ventures/portfolio",                   "accelerator"),
    ("https://workday.com/ventures/portfolio",                     "accelerator"),
    ("https://hubspot.com/ventures/portfolio",                     "accelerator"),
    ("https://twilio.org/portfolio/",                              "accelerator"),
    ("https://zoom.us/zoom-apps/companies",                        "accelerator"),

    # ── More US universities ─────────────────────────────────────────
    ("https://www.cmu.edu/swartz-center/swartz-center-portfolio/", "university_incubator"),
    ("https://www.gsb.stanford.edu/insights/center-entrepreneurial-studies/portfolio", "university_incubator"),
    ("https://innovation.uw.edu/portfolio/",                       "university_incubator"),
    ("https://innovation.case.edu/portfolio",                      "university_incubator"),
    ("https://innovation.harvard.edu/portfolio",                   "university_incubator"),
    ("https://innovation.princeton.edu/portfolio",                 "university_incubator"),
    ("https://innovation.brown.edu/portfolio",                     "university_incubator"),
    ("https://innovation.columbia.edu/portfolio",                  "university_incubator"),
    ("https://innovation.cornell.edu/portfolio",                   "university_incubator"),
    ("https://innovation.upenn.edu/portfolio",                     "university_incubator"),
    ("https://innovation.dartmouth.edu/portfolio",                 "university_incubator"),
    ("https://innovation.duke.edu/portfolio",                      "university_incubator"),
    ("https://innovation.jhu.edu/portfolio",                       "university_incubator"),
    ("https://innovation.vanderbilt.edu/portfolio",                "university_incubator"),
    ("https://innovation.wustl.edu/portfolio",                     "university_incubator"),
    ("https://innovation.berkeley.edu/portfolio",                  "university_incubator"),
    ("https://hilab.harvard.edu/portfolio",                        "university_incubator"),
    ("https://entrepreneurship.northeastern.edu/portfolio/",       "university_incubator"),
    ("https://innovation.bu.edu/portfolio",                        "university_incubator"),
    ("https://www.gatech.edu/atdc/portfolio",                      "university_incubator"),
    ("https://innovation.gatech.edu/atdc/portfolio",               "university_incubator"),
    ("https://eship.fbe.kennesaw.edu/portfolio",                   "university_incubator"),
    ("https://startup.uiowa.edu/portfolio",                        "university_incubator"),
    ("https://www.purdueresearchpark.com/portfolio",               "university_incubator"),
    ("https://www.osu.edu/innovation/portfolio",                   "university_incubator"),
    ("https://innovation.osu.edu/portfolio",                       "university_incubator"),
    ("https://innovation.psu.edu/portfolio",                       "university_incubator"),
    ("https://startup.uconn.edu/portfolio",                        "university_incubator"),
    ("https://innovation.umd.edu/portfolio",                       "university_incubator"),
    ("https://www.umich.edu/zli/portfolio",                        "university_incubator"),
    ("https://innovation.umich.edu/portfolio",                     "university_incubator"),
    ("https://innovation.gmu.edu/portfolio",                       "university_incubator"),
    ("https://startup.ufl.edu/portfolio",                          "university_incubator"),
    ("https://innovation.miami.edu/portfolio",                     "university_incubator"),
    ("https://innovation.unc.edu/portfolio",                       "university_incubator"),
    ("https://startup.indiana.edu/portfolio",                      "university_incubator"),
    ("https://innovation.iu.edu/portfolio",                        "university_incubator"),
    ("https://innovation.illinois.edu/portfolio",                  "university_incubator"),
    ("https://innovation.uic.edu/portfolio",                       "university_incubator"),
    ("https://innovation.wisconsin.edu/portfolio",                 "university_incubator"),
    ("https://innovation.umn.edu/portfolio",                       "university_incubator"),
    ("https://innovation.colorado.edu/portfolio",                  "university_incubator"),
    ("https://innovation.utah.edu/portfolio",                      "university_incubator"),
    ("https://innovation.byu.edu/portfolio",                       "university_incubator"),
    ("https://innovation.asu.edu/portfolio",                       "university_incubator"),
    ("https://startupucsd.com/portfolio",                          "university_incubator"),
    ("https://innovation.ucsd.edu/portfolio",                      "university_incubator"),
    ("https://innovation.uci.edu/portfolio",                       "university_incubator"),
    ("https://innovation.ucsf.edu/portfolio",                      "university_incubator"),
    ("https://innovation.uw.edu/portfolio",                        "university_incubator"),
    ("https://startx.stanford.edu/companies",                      "university_incubator"),
    ("https://research.berkeley.edu/portfolio",                    "university_incubator"),
    ("https://entrepreneurship.mit.edu/portfolio/",                "university_incubator"),
    ("https://martin.mit.edu/portfolio",                           "university_incubator"),
    ("https://martintrust.mit.edu/portfolio",                      "university_incubator"),
    ("https://entrepreneurship.uchicago.edu/portfolio",            "university_incubator"),
    ("https://eship.princeton.edu/portfolio",                      "university_incubator"),
    ("https://innovation.utexas.edu/portfolio",                    "university_incubator"),
    ("https://innovation.tamu.edu/portfolio",                      "university_incubator"),
    ("https://innovation.rice.edu/portfolio",                      "university_incubator"),

    # ── International universities ───────────────────────────────────
    ("https://www.imperial.ac.uk/enterprise/businesses/",          "university_incubator"),
    ("https://www.cam.ac.uk/research/innovation/portfolio",        "university_incubator"),
    ("https://www.ox.ac.uk/innovation/portfolio",                  "university_incubator"),
    ("https://www.lse.ac.uk/innovation/portfolio",                 "university_incubator"),
    ("https://www.ucl.ac.uk/enterprise/portfolio",                 "university_incubator"),
    ("https://www.kcl.ac.uk/innovation/portfolio",                 "university_incubator"),
    ("https://innovation.ed.ac.uk/portfolio",                      "university_incubator"),
    ("https://www.ethz.ch/en/industry/portfolio.html",             "university_incubator"),
    ("https://www.epfl.ch/innovation/portfolio/",                  "university_incubator"),
    ("https://www.tudelft.nl/en/about-tu-delft/portfolio",         "university_incubator"),
    ("https://www.tum.de/en/innovation/portfolio",                 "university_incubator"),
    ("https://www.kth.se/en/innovation/portfolio",                 "university_incubator"),
    ("https://www.aalto.fi/en/innovation/portfolio",               "university_incubator"),
    ("https://www.dtu.dk/english/about/portfolio",                 "university_incubator"),
    ("https://www.kaist.ac.kr/en/innovation",                      "university_incubator"),
    ("https://startup.snu.ac.kr/portfolio",                        "university_incubator"),
    ("https://innovation.nus.edu.sg/portfolio",                    "university_incubator"),
    ("https://entrepreneurship.ntu.edu.sg/portfolio",              "university_incubator"),
    ("https://www.iitb.ac.in/incubator/portfolio",                 "university_incubator"),
    ("https://www.iitm.ac.in/incubator/companies",                 "university_incubator"),
    ("https://www.iisc.ac.in/incubator/portfolio",                 "university_incubator"),
    ("https://www.tsinghua.edu.cn/en/innovation",                  "university_incubator"),
    ("https://www.pku.edu.cn/innovation/portfolio",                "university_incubator"),
    ("https://www.utokyo.ac.jp/innovation/portfolio",              "university_incubator"),
    ("https://www.kyoto-u.ac.jp/en/innovation",                    "university_incubator"),
    ("https://www.unimelb.edu.au/innovation/portfolio",            "university_incubator"),
    ("https://www.sydney.edu.au/innovation/portfolio",             "university_incubator"),
    ("https://www.monash.edu/innovation/portfolio",                "university_incubator"),
    ("https://www.toronto.ca/innovation/portfolio",                "university_incubator"),
    ("https://uoft.me/portfolio",                                  "university_incubator"),
    ("https://www.mcgill.ca/innovation/portfolio",                 "university_incubator"),
    ("https://www.uwaterloo.ca/innovation/portfolio",              "university_incubator"),
    ("https://www.ubc.ca/innovation/portfolio",                    "university_incubator"),
    ("https://www.tau.ac.il/innovation/portfolio",                 "university_incubator"),
    ("https://www.technion.ac.il/en/innovation",                   "university_incubator"),
    ("https://www.huji.ac.il/en/innovation",                       "university_incubator"),
    ("https://www.weizmann.ac.il/en/innovation",                   "university_incubator"),

    # ── International accelerators ───────────────────────────────────
    ("https://www.foundersfactory.com/portfolio",                  "accelerator"),
    ("https://www.foundamental.com/portfolio",                     "accelerator"),
    ("https://www.greentown.com/companies",                        "accelerator"),
    ("https://www.kibo-ventures.com/portfolio",                    "accelerator"),
    ("https://www.bertelsmannfoundation.org/portfolio",            "accelerator"),
    ("https://www.bigbang.no/portfolio",                           "accelerator"),
    ("https://startupinresidence.com/portfolio",                   "accelerator"),
    ("https://www.l-marks.com/portfolio",                          "accelerator"),
    ("https://www.cogniva.com/portfolio",                          "accelerator"),
    ("https://www.zwhq.com/portfolio",                             "accelerator"),
    ("https://www.thefamily.co/companies",                         "accelerator"),
    ("https://www.stationf.co/startups",                           "accelerator"),
    ("https://www.lacite.fr/companies",                            "accelerator"),
    ("https://www.bpifrance.com/portfolio",                        "accelerator"),
    ("https://www.fastforward.org/companies",                      "accelerator"),
    ("https://founderzbasic.com/portfolio",                        "accelerator"),
    ("https://www.scaling-africa.com/portfolio",                   "accelerator"),
    ("https://www.flat6labs.com/portfolio",                        "accelerator"),
    ("https://kreutz.de/portfolio",                                "accelerator"),
    ("https://www.kinglobal.com/portfolio",                        "accelerator"),
    ("https://www.collider.no/portfolio",                          "accelerator"),
    ("https://www.startupschoolwm.com/portfolio",                  "accelerator"),
    ("https://www.startuplab.no/portfolio",                        "accelerator"),
    ("https://www.spaccelerator.com/portfolio",                    "accelerator"),
    ("https://www.bootcampventures.com/portfolio",                 "accelerator"),
    ("https://www.spaceshift.io/portfolio",                        "accelerator"),
    ("https://www.skydeck.berkeley.edu/portfolio",                 "accelerator"),
    ("https://www.dreamit.com/portfolio/",                         "accelerator"),
    ("https://gener8tor.com/companies",                            "accelerator"),
    ("https://wayra.com/portfolio",                                "accelerator"),
    ("https://www.vala.org/portfolio",                             "accelerator"),
    ("https://www.cic.com/companies",                              "accelerator"),
    ("https://www.brinc.io/companies",                             "accelerator"),
    ("https://www.hcl.com/innovate/portfolio",                     "accelerator"),
    ("https://surge.peakxv.com/companies/",                        "accelerator"),
    ("https://www.iter8.com/portfolio",                            "accelerator"),
    ("https://www.kima.vc/portfolio",                              "accelerator"),
    ("https://www.eu-startups.com/directory/",                     "discovery_aggregator"),

    # ── Korean/Asian accelerators ────────────────────────────────────
    ("https://www.dcamp.kr/portfolio",                             "accelerator"),
    ("https://www.maru180.com/portfolio",                          "accelerator"),
    ("https://www.startup-alliance.or.kr/portfolio",               "accelerator"),
    ("https://kised.or.kr/portfolio",                              "government_program"),
    ("https://www.born2global.com/companies",                      "accelerator"),
    ("https://www.fastventures.co.kr/portfolio",                   "accelerator"),
    ("https://www.bonangels.com/portfolio",                        "accelerator"),
    ("https://www.sparklabs.co.kr/portfolio",                      "accelerator"),
    ("https://shiftbio.kr/portfolio",                              "accelerator"),
    ("https://www.theventures.co.kr/portfolio",                    "accelerator"),
    ("https://www.ncsoft.com/ventures/portfolio",                  "accelerator"),
    ("https://www.line-ventures.com/portfolio",                    "accelerator"),
    ("https://www.softbank-ventures.com/portfolio",                "accelerator"),
    ("https://www.kvic.or.kr/portfolio",                           "government_program"),
    ("https://www.tipa.or.kr/portfolio",                           "government_program"),
    ("https://www.zerokr.org/portfolio",                           "accelerator"),
    ("https://primer.kr/companies",                                "accelerator"),
    ("https://www.theventures.com/portfolio",                      "accelerator"),
    ("https://www.bluepoint.partners/portfolio",                   "accelerator"),
    ("https://www.musinsa-partners.com/portfolio",                 "accelerator"),
    ("https://www.kakaoinvestment.co.kr/portfolio",                "accelerator"),
    ("https://www.smileventures.co.kr/portfolio",                  "accelerator"),

    # ── International government programs ────────────────────────────
    ("https://www.innovateuk.gov.uk/projects",                     "government_program"),
    ("https://www.gov.uk/government/organisations/innovate-uk",    "government_program"),
    ("https://www.aria.org.uk/programs/",                          "government_program"),
    ("https://nrc.canada.ca/en/research-development/research-collaboration/programs/portfolio", "government_program"),
    ("https://nrc-cnrc.gc.ca/eng/irap/portfolio",                  "government_program"),
    ("https://www.businessfinland.fi/en/portfolio",                "government_program"),
    ("https://www.vinnova.se/en/projects/",                        "government_program"),
    ("https://www.tubitak.gov.tr/en/funds-and-programs",           "government_program"),
    ("https://www.innovationisrael.org.il/en/portfolio",           "government_program"),
    ("https://www.innovation.gov.au/portfolio",                    "government_program"),
    ("https://csiro.au/innovation/portfolio",                      "government_program"),
    ("https://www.csiro.au/en/work-with-us/innovation",            "government_program"),
    ("https://www.cdti.es/en/projects",                            "government_program"),
    ("https://www.bpifrance.com/innovation/projects",              "government_program"),
    ("https://www.bmbf.de/en/projects",                            "government_program"),
    ("https://www.commission.europa.eu/eic-portfolio",             "government_program"),
    ("https://eic.ec.europa.eu/eic-funded-projects",               "government_program"),
    ("https://www.horizon-europe.eu/projects",                     "government_program"),
    ("https://kistiportfolio.kr/projects",                         "government_program"),
    ("https://www.jst.go.jp/en/programs",                          "government_program"),
    ("https://www.nedo.go.jp/english/portfolio",                   "government_program"),
    ("https://www.nrf.gov.sg/portfolio",                           "government_program"),
    ("https://www.startupsg.gov.sg/companies",                     "government_program"),
    ("https://www.dst.gov.in/projects",                            "government_program"),
    ("https://startupindia.gov.in/content/sih/en/recognized-startups.html", "government_program"),

    # ── More AI-specific accelerators / grants ────────────────────────
    ("https://aigrant.com/companies",                              "accelerator"),
    ("https://cohere.com/grant",                                   "accelerator"),
    ("https://openai.fund/portfolio",                              "vc_portfolio"),
    ("https://www.anthropic.com/customers",                        "vc_portfolio"),
    ("https://nvidiainception.com/companies",                      "accelerator"),
    ("https://aws.amazon.com/generative-ai-accelerator/",          "accelerator"),
    ("https://startup.googleforstartups.com/ai/",                  "accelerator"),
    ("https://www.microsoft.com/en-us/startups/ai",                "accelerator"),
    ("https://www.scaleai.com/customers",                          "vc_portfolio"),

    # ── Discovery / aggregator additions ─────────────────────────────
    ("https://betalist.com/popular",                               "discovery_aggregator"),
    ("https://wellfound.com/discover",                             "discovery_aggregator"),
    ("https://www.crunchbase.com/discover/organization.companies/", "discovery_aggregator"),
    ("https://eu-startups.com/category/funding/",                  "discovery_aggregator"),
    ("https://thenextweb.com/news/category/startups",              "discovery_aggregator"),
    ("https://techcrunch.com/category/startups/",                  "discovery_aggregator"),
    ("https://www.startupgrind.com/directory/",                    "discovery_aggregator"),
    ("https://www.indiehackers.com/products",                      "discovery_aggregator"),
    ("https://www.producthunt.com/launches",                       "discovery_aggregator"),
    ("https://startups.com/library/companies",                     "discovery_aggregator"),
    ("https://www.cbinsights.com/research-list-of-ai-100-startups", "discovery_aggregator"),
    ("https://www.cbinsights.com/research/ai-50-startups",         "discovery_aggregator"),
    ("https://news.ycombinator.com/show",                          "discovery_aggregator"),
    ("https://github.com/topics/artificial-intelligence?type=Organization", "discovery_aggregator"),
    ("https://github.com/collections/learn-to-code",               "discovery_aggregator"),
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be added without touching the DB")
    args = p.parse_args()

    # Pre-compute existing domains so we can report skip vs add accurately.
    with session_scope() as session:
        existing = {d for (d,) in session.query(SiteHealth.domain).all()}

    monitor = HealthMonitor() if not args.dry_run else None

    added: list[tuple[str, str, str]] = []  # (domain, url, category)
    skipped: list[tuple[str, str]] = []     # (domain, reason)
    bad: list[str] = []

    for url, category in CURATED:
        domain = canonicalize_domain(url)
        if not domain:
            bad.append(url)
            continue
        if domain in existing:
            skipped.append((domain, "already registered"))
            continue
        if any(a[0] == domain for a in added):
            skipped.append((domain, "duplicate in curated list"))
            continue

        if args.dry_run:
            added.append((domain, url, category))
            continue

        monitor.register_site(
            domain=domain,
            url=url,
            difficulty="hard",
            scraper_name=f"curated:{category}",
        )
        # register_site doesn't take category — patch it directly.
        with session_scope() as session:
            row = session.query(SiteHealth).filter(SiteHealth.domain == domain).first()
            if row is not None and not row.category:
                row.category = category
        added.append((domain, url, category))

    # Summary
    by_cat: dict[str, int] = {}
    for _, _, c in added:
        by_cat[c] = by_cat.get(c, 0) + 1

    mode = "DRY-RUN" if args.dry_run else "registered"
    print(f"\n=== {mode}: {len(added)} new sites ===")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"  {cat:24s} {n:3d}")
    print(f"\nSkipped (existing/dup): {len(skipped)}")
    if bad:
        print(f"Unparseable URLs: {len(bad)}")
        for u in bad:
            print(f"  {u}")


if __name__ == "__main__":
    main()
