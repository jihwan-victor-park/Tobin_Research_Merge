# Pending Scraper Failure Buckets

Total pending sites analyzed: **460**

## Summary

| Bucket | Count | Fix recommendation |
|---|---:|---|
| **H_DEAD_SITE** | 71 | Domain unreachable / parked / LLM-hallucinated → drop from inventory |
| **I_OFFTOPIC** | 69 | Domain alive but homepage has zero startup/VC/portfolio keywords → likely wrong site, drop or downgrade |
| **C_HTTP_BLOCKED** | 20 | HTTP 403 / 429 / blocked by anti-bot → fix with proxy + UA rotation |
| **B_ANTI_BOT_JS** | 0 | Tavily/fetch returned thin content, likely JS-only or bot-blocked → Playwright + stealth |
| **E_PARSE_FAIL** | 0 | LLM extraction returned invalid JSON / unparseable → tighten prompt or use tool_use mode |
| **F_PAGINATION** | 0 | Pagination hints present but agent budget exceeded → bump budget / pagination strategy |
| **D_WRONG_URL** | 223 | Page fetched fine but 0 records — seed URL points at wrong page → re-discover with LLM web search |
| **G_STRUCTURE_BROKEN** | 6 | Site fetches fine, instructions exist, repeated 0-records → no portfolio page, swap to aggregator |
| **A_NEVER_TRIED** | 43 | 0 runs and live probe looks fine → just queue it |
| **Z_UNKNOWN** | 28 | Did not match any rule — needs manual look |

## Samples per bucket (up to 10)

### H_DEAD_SITE (71)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| aef.hk | 0 | - dns_fail | DNS lookup failed |
| true.vc | 1 | - dns_fail | DNS lookup failed |
| kholsaventures.com | 1 | - dns_fail | DNS lookup failed |
| pi.capital | 1 | - dns_fail | DNS lookup failed |
| spaccelerator.com | 1 | 200 OK | Parked / for-sale page |
| zinclaunch.com | 1 | - dns_fail | DNS lookup failed |
| dmzaccelerator.com | 1 | - dns_fail | DNS lookup failed |
| gw-ileg.org | 1 | - dns_fail | DNS lookup failed |
| kentstateaccelerator.com | 1 | - dns_fail | DNS lookup failed |
| newchip.com | 1 | - dns_fail | DNS lookup failed |

### I_OFFTOPIC (69)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| benchmark.com | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| climate-kic.org | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| gov.uk | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| cdti.es | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| dartmouth.edu | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| indiehackers.com | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| github.com | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| usc.edu | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| innovationisrael.org.il | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |
| duke.edu | 1 | 200 OK | No startup/VC/portfolio keywords on homepage |

### C_HTTP_BLOCKED (20)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| boomtownaccelerator.com | 1 | 403 fail | HTTP 403/429 or block keyword |
| unimelb.edu.au | 1 | 403 fail | HTTP 403/429 or block keyword |
| umich.edu | 1 | 403 fail | HTTP 403/429 or block keyword |
| pitchbook.com | 1 | 403 fail | HTTP 403/429 or block keyword |
| oracle.com | 1 | 403 fail | HTTP 403/429 or block keyword |
| intel.com | 1 | 403 fail | HTTP 403/429 or block keyword |
| jhu.edu | 1 | 403 fail | HTTP 403/429 or block keyword |
| ucsf.edu | 1 | 403 fail | HTTP 403/429 or block keyword |
| ox.ac.uk | 1 | 403 fail | HTTP 403/429 or block keyword |
| monash.edu | 1 | 403 fail | HTTP 403/429 or block keyword |

### D_WRONG_URL (223)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| thrivecap.com | 1 | 200 OK | Page reachable but 0 records extracted |
| capitalinnovators.com | 1 | 200 OK | Page reachable but 0 records extracted |
| initialized.com | 1 | 200 OK | Page reachable but 0 records extracted |
| ivp.com | 2 | 200 OK | Page reachable but 0 records extracted |
| creandum.com | 1 | 200 OK | Page reachable but 0 records extracted |
| kap.kr | 1 | 200 OK | Page reachable but 0 records extracted |
| emcap.com | 2 | 200 OK | Page reachable but 0 records extracted |
| gobiventures.com | 1 | 200 OK | Page reachable but 0 records extracted |
| nexusvp.com | 1 | 200 OK | Page reachable but 0 records extracted |
| tigerglobal.com | 1 | 200 OK | Page reachable but 0 records extracted |

### G_STRUCTURE_BROKEN (6)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| 8vc.com | 3 | 200 OK | Instructions exist, repeated 0-records |
| berkeley.edu | 2 | 200 OK | Instructions exist, repeated 0-records |
| masschallenge.org | 1 | 200 OK | Instructions exist, repeated 0-records |
| accel.com | 1 | 200 OK | Instructions exist, repeated 0-records |
| nea.com | 1 | 200 OK | Instructions exist, repeated 0-records |
| lsvp.com | 1 | 200 OK | Instructions exist, repeated 0-records |

### A_NEVER_TRIED (43)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| alliance.rice.edu | 0 | 200 OK | 0 runs, probe OK |
| technation.io | 0 | 200 OK | 0 runs, probe OK |
| kellercenter.princeton.edu | 0 | 200 OK | 0 runs, probe OK |
| startups.columbia.edu | 0 | 200 OK | 0 runs, probe OK |
| entrepreneurship.mit.edu | 0 | 200 OK | 0 runs, probe OK |
| crunchbase.com | 0 | 200 OK | 0 runs, probe OK |
| jfdi.asia | 0 | 200 OK | 0 runs, probe OK |
| allvp.vc | 0 | 200 OK | 0 runs, probe OK |
| sheraa.ae | 0 | 200 OK | 0 runs, probe OK |
| turn8.co | 0 | 200 OK | 0 runs, probe OK |

### Z_UNKNOWN (28)

| Domain | Runs | Probe | Reason |
|---|---:|---|---|
| innovate360.co | 0 | - conn:SSLError | runs=0 probe_ok=False err=none |
| pearvc.com | 1 | - conn:SSLError | runs=1 probe_ok=False err=none |
| beondeck.com | 1 | - conn:ConnectionError | runs=1 probe_ok=False err=none |
| altimetercapital.com | 1 | - conn:SSLError | runs=1 probe_ok=False err=none |
| blackstonelaunchpad.org | 1 | - conn:ConnectTimeout | runs=1 probe_ok=False err=none |
| blueprint.kr | 1 | - conn:ConnectTimeout | runs=1 probe_ok=False err=none |
| canada.ca | 1 | - conn:ConnectionError | runs=1 probe_ok=False err=anthropic api error (400): error code: 400 - {'type': 'error |
| innovation.gov.au | 1 | - conn:ConnectionError | runs=1 probe_ok=False err=anthropic api error (400): error code: 400 - {'type': 'error |
| kstartup.go.kr | 1 | - conn:ConnectionError | runs=1 probe_ok=False err=none |
| lightspeedvp.com | 1 | - conn:SSLError | runs=1 probe_ok=False err=none |

## Full domain → bucket mapping

```
H_DEAD_SITE	aef.hk
H_DEAD_SITE	true.vc
H_DEAD_SITE	kholsaventures.com
H_DEAD_SITE	pi.capital
H_DEAD_SITE	spaccelerator.com
H_DEAD_SITE	zinclaunch.com
H_DEAD_SITE	dmzaccelerator.com
H_DEAD_SITE	gw-ileg.org
H_DEAD_SITE	kentstateaccelerator.com
H_DEAD_SITE	newchip.com
H_DEAD_SITE	startuplisboa.com
H_DEAD_SITE	nyuentrepreneur.org
H_DEAD_SITE	andreessen.com
H_DEAD_SITE	andreessen-horowitz.com
H_DEAD_SITE	thrive.cm
H_DEAD_SITE	cota-capital.com
H_DEAD_SITE	citi-ventures.com
H_DEAD_SITE	gradientventures.com
H_DEAD_SITE	newtheoryvc.com
H_DEAD_SITE	basisset.vc
H_DEAD_SITE	the-catalyst.io
H_DEAD_SITE	union-square-ventures.com
H_DEAD_SITE	financialventureslab.com
H_DEAD_SITE	commerce-ventures.com
H_DEAD_SITE	drago.capital
H_DEAD_SITE	hackvc.com
H_DEAD_SITE	frst.capital
H_DEAD_SITE	elaiacap.com
H_DEAD_SITE	grindstoneaccelerator.co.za
H_DEAD_SITE	greenhousecapital.co.za
H_DEAD_SITE	oncedeck.com
H_DEAD_SITE	cambridgeseedfund.com
H_DEAD_SITE	brent-hoberman.com
H_DEAD_SITE	nordicninjavc.com
H_DEAD_SITE	naverd2.com
H_DEAD_SITE	mirae-asset.com
H_DEAD_SITE	elevation.cap
H_DEAD_SITE	thirdderivative.org
H_DEAD_SITE	urban-x.com
H_DEAD_SITE	venturesforamerica.org
H_DEAD_SITE	afore.com
H_DEAD_SITE	greenrubinoinc.com
H_DEAD_SITE	nvidiainceptioneco.com
H_DEAD_SITE	startupucsd.com
H_DEAD_SITE	greentown.com
H_DEAD_SITE	kibo-ventures.com
H_DEAD_SITE	utokyo.ac.jp
H_DEAD_SITE	l-marks.com
H_DEAD_SITE	lacite.fr
H_DEAD_SITE	founderzbasic.com
H_DEAD_SITE	scaling-africa.com
H_DEAD_SITE	collider.no
H_DEAD_SITE	startupschoolwm.com
H_DEAD_SITE	startup-alliance.or.kr
H_DEAD_SITE	shiftbio.kr
H_DEAD_SITE	theventures.co.kr
H_DEAD_SITE	softbank-ventures.com
H_DEAD_SITE	scaleai.com
H_DEAD_SITE	zerokr.org
H_DEAD_SITE	bluepoint.partners
H_DEAD_SITE	musinsa-partners.com
H_DEAD_SITE	horizon-europe.eu
H_DEAD_SITE	smileventures.co.kr
H_DEAD_SITE	kistiportfolio.kr
H_DEAD_SITE	nvidiainception.com
H_DEAD_SITE	iccelerate.com
H_DEAD_SITE	bootcampventures.com
H_DEAD_SITE	line-ventures.com
H_DEAD_SITE	agentic_engine
H_DEAD_SITE	energizecapital.com
H_DEAD_SITE	aitoolhunt.com
I_OFFTOPIC	benchmark.com
I_OFFTOPIC	climate-kic.org
I_OFFTOPIC	gov.uk
I_OFFTOPIC	cdti.es
I_OFFTOPIC	dartmouth.edu
I_OFFTOPIC	indiehackers.com
I_OFFTOPIC	github.com
I_OFFTOPIC	usc.edu
I_OFFTOPIC	innovationisrael.org.il
I_OFFTOPIC	duke.edu
I_OFFTOPIC	gatech.edu
I_OFFTOPIC	gmu.edu
I_OFFTOPIC	uic.edu
I_OFFTOPIC	uci.edu
I_OFFTOPIC	lse.ac.uk
I_OFFTOPIC	workbench.vc
I_OFFTOPIC	breyer.com
I_OFFTOPIC	kompasvc.com
I_OFFTOPIC	case.edu
I_OFFTOPIC	bolt.io
I_OFFTOPIC	amaesgroup.com
I_OFFTOPIC	bu.edu
I_OFFTOPIC	psu.edu
I_OFFTOPIC	ufl.edu
I_OFFTOPIC	iu.edu
I_OFFTOPIC	wisconsin.edu
I_OFFTOPIC	insidr.ai
I_OFFTOPIC	nus.edu.sg
I_OFFTOPIC	ntu.edu.sg
I_OFFTOPIC	tsinghua.edu.cn
I_OFFTOPIC	pku.edu.cn
I_OFFTOPIC	weizmann.ac.il
I_OFFTOPIC	kvic.or.kr
I_OFFTOPIC	dang.ai
I_OFFTOPIC	tipa.or.kr
I_OFFTOPIC	kreutz.de
I_OFFTOPIC	kinglobal.com
I_OFFTOPIC	spaceshift.io
I_OFFTOPIC	f6s.com
I_OFFTOPIC	csiro.au
I_OFFTOPIC	bmbf.de
I_OFFTOPIC	europa.eu
I_OFFTOPIC	microlaunch.net
I_OFFTOPIC	wustl.edu
I_OFFTOPIC	osu.edu
I_OFFTOPIC	epfl.ch
I_OFFTOPIC	tum.de
I_OFFTOPIC	dtu.dk
I_OFFTOPIC	toronto.ca
I_OFFTOPIC	ihub.co.ke
I_OFFTOPIC	galvanize.com
I_OFFTOPIC	preferredbynature.org
I_OFFTOPIC	getworm.com
I_OFFTOPIC	amazon.com
I_OFFTOPIC	qualcomm.com
I_OFFTOPIC	snowflake.com
I_OFFTOPIC	hubspot.com
I_OFFTOPIC	bigbang.no
I_OFFTOPIC	saasaitools.com
I_OFFTOPIC	thefamily.co
I_OFFTOPIC	born2global.com
I_OFFTOPIC	cohere.com
I_OFFTOPIC	shasta.vc
I_OFFTOPIC	hashed.com
I_OFFTOPIC	anthropic.com
I_OFFTOPIC	aitools.fyi
I_OFFTOPIC	toolify.ai
I_OFFTOPIC	crozdesk.com
I_OFFTOPIC	saasworthy.com
C_HTTP_BLOCKED	boomtownaccelerator.com
C_HTTP_BLOCKED	unimelb.edu.au
C_HTTP_BLOCKED	umich.edu
C_HTTP_BLOCKED	pitchbook.com
C_HTTP_BLOCKED	oracle.com
C_HTTP_BLOCKED	intel.com
C_HTTP_BLOCKED	jhu.edu
C_HTTP_BLOCKED	ucsf.edu
C_HTTP_BLOCKED	ox.ac.uk
C_HTTP_BLOCKED	monash.edu
C_HTTP_BLOCKED	startupinresidence.com
C_HTTP_BLOCKED	startupbuffer.com
C_HTTP_BLOCKED	hubspotventures.com
C_HTTP_BLOCKED	disney.com
C_HTTP_BLOCKED	hawksridge.com
C_HTTP_BLOCKED	capterra.com
C_HTTP_BLOCKED	getapp.com
C_HTTP_BLOCKED	g2.com
C_HTTP_BLOCKED	alternativeto.net
C_HTTP_BLOCKED	sourceforge.net
D_WRONG_URL	thrivecap.com
D_WRONG_URL	capitalinnovators.com
D_WRONG_URL	initialized.com
D_WRONG_URL	ivp.com
D_WRONG_URL	creandum.com
D_WRONG_URL	kap.kr
D_WRONG_URL	emcap.com
D_WRONG_URL	gobiventures.com
D_WRONG_URL	nexusvp.com
D_WRONG_URL	tigerglobal.com
D_WRONG_URL	upfront.com
D_WRONG_URL	floodgate.com
D_WRONG_URL	zaffire.com
D_WRONG_URL	canaan.com
D_WRONG_URL	nvidia.com
D_WRONG_URL	launchhouse.com
D_WRONG_URL	iconiqcapital.com
D_WRONG_URL	stripe.com
D_WRONG_URL	cloudflare.com
D_WRONG_URL	menloventures.com
D_WRONG_URL	workday.com
D_WRONG_URL	matrixpartners.com
D_WRONG_URL	ucsd.edu
D_WRONG_URL	cam.ac.uk
D_WRONG_URL	kcl.ac.uk
D_WRONG_URL	tudelft.nl
D_WRONG_URL	conviction.com
D_WRONG_URL	aalto.fi
D_WRONG_URL	iitm.ac.in
D_WRONG_URL	yale.edu
D_WRONG_URL	uoft.me
D_WRONG_URL	upenn.edu
D_WRONG_URL	ubc.ca
D_WRONG_URL	technion.ac.il
D_WRONG_URL	50partners.fr
D_WRONG_URL	hcl.com
D_WRONG_URL	ncsoft.com
D_WRONG_URL	bethnalgreenventures.com
D_WRONG_URL	nrc-cnrc.gc.ca
D_WRONG_URL	tubitak.gov.tr
D_WRONG_URL	thefoundry.com
D_WRONG_URL	nrf.gov.sg
D_WRONG_URL	khoslaventures.com
D_WRONG_URL	northwestern.edu
D_WRONG_URL	thenextweb.com
D_WRONG_URL	darpa.mil
D_WRONG_URL	sba.gov
D_WRONG_URL	k-startup.go.kr
D_WRONG_URL	utexas.edu
D_WRONG_URL	aria.org.uk
D_WRONG_URL	ucla.edu
D_WRONG_URL	washington.edu
D_WRONG_URL	primer.kr
D_WRONG_URL	businessfinland.fi
D_WRONG_URL	vinnova.se
D_WRONG_URL	jst.go.jp
D_WRONG_URL	nedo.go.jp
D_WRONG_URL	startupsg.gov.sg
D_WRONG_URL	dst.gov.in
D_WRONG_URL	startupindia.gov.in
D_WRONG_URL	cornell.edu
D_WRONG_URL	cdtm.com
D_WRONG_URL	uchicago.edu
D_WRONG_URL	startupgrind.com
D_WRONG_URL	stanford.edu
D_WRONG_URL	brandery.org
D_WRONG_URL	unc.edu
D_WRONG_URL	utah.edu
D_WRONG_URL	asu.edu
D_WRONG_URL	imperial.ac.uk
D_WRONG_URL	socialcapital.com
D_WRONG_URL	boxgroup.com
D_WRONG_URL	scout-vc.com
D_WRONG_URL	zettavp.com
D_WRONG_URL	section32.com
D_WRONG_URL	ribbitcapital.com
D_WRONG_URL	eqtventures.com
D_WRONG_URL	cherry.vc
D_WRONG_URL	foundersinc.com
D_WRONG_URL	dayoneventures.com
D_WRONG_URL	partechpartners.com
D_WRONG_URL	earlybird.com
D_WRONG_URL	softbank.com
D_WRONG_URL	gsr.vc
D_WRONG_URL	lightboxvc.com
D_WRONG_URL	uw.edu
D_WRONG_URL	petri.bio
D_WRONG_URL	activate.org
D_WRONG_URL	elemental.org
D_WRONG_URL	entrepreneurfirst.com
D_WRONG_URL	greatpoint.com
D_WRONG_URL	brown.edu
D_WRONG_URL	purdueresearchpark.com
D_WRONG_URL	vanderbilt.edu
D_WRONG_URL	miami.edu
D_WRONG_URL	umn.edu
D_WRONG_URL	kennesaw.edu
D_WRONG_URL	uiowa.edu
D_WRONG_URL	uconn.edu
D_WRONG_URL	indiana.edu
D_WRONG_URL	illinois.edu
D_WRONG_URL	colorado.edu
D_WRONG_URL	byu.edu
D_WRONG_URL	tamu.edu
D_WRONG_URL	ed.ac.uk
D_WRONG_URL	kaist.ac.kr
D_WRONG_URL	huji.ac.il
D_WRONG_URL	kised.or.kr
D_WRONG_URL	fastforward.org
D_WRONG_URL	startuplab.no
D_WRONG_URL	vala.org
D_WRONG_URL	dcamp.kr
D_WRONG_URL	fastventures.co.kr
D_WRONG_URL	openai.fund
D_WRONG_URL	startups.com
D_WRONG_URL	kakaoinvestment.co.kr
D_WRONG_URL	harvard.edu
D_WRONG_URL	northeastern.edu
D_WRONG_URL	ucl.ac.uk
D_WRONG_URL	ethz.ch
D_WRONG_URL	kth.se
D_WRONG_URL	snu.ac.kr
D_WRONG_URL	iitb.ac.in
D_WRONG_URL	iisc.ac.in
D_WRONG_URL	kyoto-u.ac.jp
D_WRONG_URL	sydney.edu.au
D_WRONG_URL	mcgill.ca
D_WRONG_URL	uwaterloo.ca
D_WRONG_URL	tau.ac.il
D_WRONG_URL	creativedestructionlab.com
D_WRONG_URL	expa.com
D_WRONG_URL	startupreserve.com
D_WRONG_URL	foundercentric.com
D_WRONG_URL	google.com
D_WRONG_URL	ai2incubator.com
D_WRONG_URL	pioneer.app
D_WRONG_URL	tampabaywave.org
D_WRONG_URL	1871.com
D_WRONG_URL	flatironschool.com
D_WRONG_URL	lemnos.vc
D_WRONG_URL	indiebio.co
D_WRONG_URL	greentownlabs.com
D_WRONG_URL	newlab.com
D_WRONG_URL	nexusgrowth.com
D_WRONG_URL	microsoft.com
D_WRONG_URL	salesforce.com
D_WRONG_URL	shopify.engineering
D_WRONG_URL	spacex.com
D_WRONG_URL	databricks.com
D_WRONG_URL	twilio.org
D_WRONG_URL	zoom.us
D_WRONG_URL	foundersfactory.com
D_WRONG_URL	foundamental.com
D_WRONG_URL	bpifrance.com
D_WRONG_URL	cic.com
D_WRONG_URL	brinc.io
D_WRONG_URL	kima.vc
D_WRONG_URL	theventures.com
D_WRONG_URL	gv.com
D_WRONG_URL	kleinerperkins.com
D_WRONG_URL	mayfield.com
D_WRONG_URL	nvp.com
D_WRONG_URL	battery.com
D_WRONG_URL	usv.com
D_WRONG_URL	firstround.com
D_WRONG_URL	coatue.com
D_WRONG_URL	meritechcapital.com
D_WRONG_URL	sapphireventures.com
D_WRONG_URL	altos.vc
D_WRONG_URL	insightpartners.com
D_WRONG_URL	dragoneer.com
D_WRONG_URL	eclipse.vc
D_WRONG_URL	lererhippeau.com
D_WRONG_URL	costanoa.vc
D_WRONG_URL	dcm.com
D_WRONG_URL	hmlt.com
D_WRONG_URL	lookoutvc.com
D_WRONG_URL	northzone.com
D_WRONG_URL	sozocap.com
D_WRONG_URL	essence.vc
D_WRONG_URL	innovationendeavors.com
D_WRONG_URL	dcvc.com
D_WRONG_URL	glasswing.vc
D_WRONG_URL	leadedge.com
D_WRONG_URL	sandhillangels.com
D_WRONG_URL	emergencecapital.com
D_WRONG_URL	uphonest.com
D_WRONG_URL	southparkcommons.com
D_WRONG_URL	bevc.com
D_WRONG_URL	flagshippioneering.com
D_WRONG_URL	polarispartners.com
D_WRONG_URL	qedinvestors.com
D_WRONG_URL	anthemis.com
D_WRONG_URL	a16zcrypto.com
D_WRONG_URL	multicoin.capital
D_WRONG_URL	placeholder.vc
D_WRONG_URL	variant.fund
D_WRONG_URL	atomico.com
D_WRONG_URL	localglobe.vc
D_WRONG_URL	speedinvest.com
D_WRONG_URL	lakestar.com
D_WRONG_URL	holtzbrinckventures.com
D_WRONG_URL	pointnine.com
D_WRONG_URL	connectventures.co
D_WRONG_URL	kinnevik.com
D_WRONG_URL	gobi.vc
D_WRONG_URL	kakaoventures.com
D_WRONG_URL	smilegate.com
D_WRONG_URL	chaivc.com
D_WRONG_URL	matrixpartners.in
D_WRONG_URL	peakxv.com
D_WRONG_URL	redpoint.com
D_WRONG_URL	fasttrackmalmo.com
D_WRONG_URL	rice.edu
D_WRONG_URL	startupwiseguys.com
D_WRONG_URL	columbia.edu
D_WRONG_URL	crv.com
D_WRONG_URL	virginia.edu
D_WRONG_URL	sbir.gov
D_WRONG_URL	amplifypartners.com
D_WRONG_URL	primary.vc
D_WRONG_URL	gigafund.com
D_WRONG_URL	lowercarboncapital.com
G_STRUCTURE_BROKEN	8vc.com
G_STRUCTURE_BROKEN	berkeley.edu
G_STRUCTURE_BROKEN	masschallenge.org
G_STRUCTURE_BROKEN	accel.com
G_STRUCTURE_BROKEN	nea.com
G_STRUCTURE_BROKEN	lsvp.com
A_NEVER_TRIED	alliance.rice.edu
A_NEVER_TRIED	technation.io
A_NEVER_TRIED	kellercenter.princeton.edu
A_NEVER_TRIED	startups.columbia.edu
A_NEVER_TRIED	entrepreneurship.mit.edu
A_NEVER_TRIED	crunchbase.com
A_NEVER_TRIED	jfdi.asia
A_NEVER_TRIED	allvp.vc
A_NEVER_TRIED	sheraa.ae
A_NEVER_TRIED	turn8.co
A_NEVER_TRIED	iceaddis.com
A_NEVER_TRIED	startx.com
A_NEVER_TRIED	topai.tools
A_NEVER_TRIED	neo.com
A_NEVER_TRIED	sosv.com
A_NEVER_TRIED	pioneerfund.vc
A_NEVER_TRIED	topstartups.io
A_NEVER_TRIED	tracxn.com
A_NEVER_TRIED	startupranking.com
A_NEVER_TRIED	openvc.app
A_NEVER_TRIED	thehub.io
A_NEVER_TRIED	startups.gallery
A_NEVER_TRIED	nationalstartupsdirectory.com
A_NEVER_TRIED	startupnationcentral.org
A_NEVER_TRIED	startupstash.com
A_NEVER_TRIED	startupjohn.com
A_NEVER_TRIED	startupinspire.com
A_NEVER_TRIED	startup88.com
A_NEVER_TRIED	startupbase.io
A_NEVER_TRIED	killerstartups.com
A_NEVER_TRIED	launchingnext.com
A_NEVER_TRIED	startupguys.net
A_NEVER_TRIED	launched.io
A_NEVER_TRIED	startuptabs.com
A_NEVER_TRIED	huggingface.co
A_NEVER_TRIED	endeavor.org
A_NEVER_TRIED	eitdigital.eu
A_NEVER_TRIED	lmarks.com
A_NEVER_TRIED	h-farm.com
A_NEVER_TRIED	ai-startups.org
A_NEVER_TRIED	stackshare.io
A_NEVER_TRIED	appsruntheworld.com
A_NEVER_TRIED	softwareworld.co
Z_UNKNOWN	innovate360.co
Z_UNKNOWN	pearvc.com
Z_UNKNOWN	beondeck.com
Z_UNKNOWN	altimetercapital.com
Z_UNKNOWN	blackstonelaunchpad.org
Z_UNKNOWN	blueprint.kr
Z_UNKNOWN	canada.ca
Z_UNKNOWN	innovation.gov.au
Z_UNKNOWN	kstartup.go.kr
Z_UNKNOWN	lightspeedvp.com
Z_UNKNOWN	norwestvp.com
Z_UNKNOWN	bowerycapital.com
Z_UNKNOWN	pradaria.com
Z_UNKNOWN	nuventures.com
Z_UNKNOWN	archvp.com
Z_UNKNOWN	oxfordseedfund.com
Z_UNKNOWN	matterchicago.com
Z_UNKNOWN	entrepreneurfirst.org.uk
Z_UNKNOWN	bertelsmannfoundation.org
Z_UNKNOWN	cogniva.com
Z_UNKNOWN	zwhq.com
Z_UNKNOWN	iter8.com
Z_UNKNOWN	maru180.com
Z_UNKNOWN	bonangels.com
Z_UNKNOWN	innovateuk.gov.uk
Z_UNKNOWN	startuplift.com
Z_UNKNOWN	googleforstartups.com
Z_UNKNOWN	feedmyapp.com
```