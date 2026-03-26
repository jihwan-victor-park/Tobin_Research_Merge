"""
Top 100 US Universities for Accelerator Discovery
Source: US News Rankings, research output, entrepreneurship programs
"""

TOP_US_UNIVERSITIES = [
    # Tier 1: Major research universities with known startup programs
    {'name': 'Stanford University', 'short': 'stanford', 'domain': 'stanford.edu', 'state': 'CA'},
    {'name': 'Massachusetts Institute of Technology', 'short': 'mit', 'domain': 'mit.edu', 'state': 'MA'},
    {'name': 'Harvard University', 'short': 'harvard', 'domain': 'harvard.edu', 'state': 'MA'},
    {'name': 'University of California Berkeley', 'short': 'berkeley', 'domain': 'berkeley.edu', 'state': 'CA'},
    {'name': 'Carnegie Mellon University', 'short': 'cmu', 'domain': 'cmu.edu', 'state': 'PA'},
    {'name': 'University of Pennsylvania', 'short': 'upenn', 'domain': 'upenn.edu', 'state': 'PA'},
    {'name': 'Cornell University', 'short': 'cornell', 'domain': 'cornell.edu', 'state': 'NY'},
    {'name': 'Columbia University', 'short': 'columbia', 'domain': 'columbia.edu', 'state': 'NY'},
    {'name': 'Princeton University', 'short': 'princeton', 'domain': 'princeton.edu', 'state': 'NJ'},
    {'name': 'Yale University', 'short': 'yale', 'domain': 'yale.edu', 'state': 'CT'},

    # Tier 2: Strong engineering/CS programs
    {'name': 'University of Michigan', 'short': 'umich', 'domain': 'umich.edu', 'state': 'MI'},
    {'name': 'Georgia Institute of Technology', 'short': 'gatech', 'domain': 'gatech.edu', 'state': 'GA'},
    {'name': 'University of Illinois Urbana-Champaign', 'short': 'illinois', 'domain': 'illinois.edu', 'state': 'IL'},
    {'name': 'University of Texas Austin', 'short': 'utexas', 'domain': 'utexas.edu', 'state': 'TX'},
    {'name': 'University of Washington', 'short': 'uw', 'domain': 'washington.edu', 'state': 'WA'},
    {'name': 'Northwestern University', 'short': 'northwestern', 'domain': 'northwestern.edu', 'state': 'IL'},
    {'name': 'Duke University', 'short': 'duke', 'domain': 'duke.edu', 'state': 'NC'},
    {'name': 'University of California Los Angeles', 'short': 'ucla', 'domain': 'ucla.edu', 'state': 'CA'},
    {'name': 'University of California San Diego', 'short': 'ucsd', 'domain': 'ucsd.edu', 'state': 'CA'},
    {'name': 'University of Southern California', 'short': 'usc', 'domain': 'usc.edu', 'state': 'CA'},

    # Tier 3: Growing entrepreneurship programs
    {'name': 'New York University', 'short': 'nyu', 'domain': 'nyu.edu', 'state': 'NY'},
    {'name': 'Boston University', 'short': 'bu', 'domain': 'bu.edu', 'state': 'MA'},
    {'name': 'University of Chicago', 'short': 'uchicago', 'domain': 'uchicago.edu', 'state': 'IL'},
    {'name': 'Rice University', 'short': 'rice', 'domain': 'rice.edu', 'state': 'TX'},
    {'name': 'Vanderbilt University', 'short': 'vanderbilt', 'domain': 'vanderbilt.edu', 'state': 'TN'},
    {'name': 'Emory University', 'short': 'emory', 'domain': 'emory.edu', 'state': 'GA'},
    {'name': 'University of North Carolina Chapel Hill', 'short': 'unc', 'domain': 'unc.edu', 'state': 'NC'},
    {'name': 'University of Virginia', 'short': 'uva', 'domain': 'virginia.edu', 'state': 'VA'},
    {'name': 'University of Wisconsin Madison', 'short': 'wisc', 'domain': 'wisc.edu', 'state': 'WI'},
    {'name': 'University of Maryland', 'short': 'umd', 'domain': 'umd.edu', 'state': 'MD'},

    # Tier 4: State flagships and tech schools
    {'name': 'Purdue University', 'short': 'purdue', 'domain': 'purdue.edu', 'state': 'IN'},
    {'name': 'Ohio State University', 'short': 'osu', 'domain': 'osu.edu', 'state': 'OH'},
    {'name': 'University of Florida', 'short': 'ufl', 'domain': 'ufl.edu', 'state': 'FL'},
    {'name': 'University of California Irvine', 'short': 'uci', 'domain': 'uci.edu', 'state': 'CA'},
    {'name': 'University of California Davis', 'short': 'ucdavis', 'domain': 'ucdavis.edu', 'state': 'CA'},
    {'name': 'University of California Santa Barbara', 'short': 'ucsb', 'domain': 'ucsb.edu', 'state': 'CA'},
    {'name': 'Pennsylvania State University', 'short': 'psu', 'domain': 'psu.edu', 'state': 'PA'},
    {'name': 'University of Minnesota', 'short': 'umn', 'domain': 'umn.edu', 'state': 'MN'},
    {'name': 'University of Colorado Boulder', 'short': 'colorado', 'domain': 'colorado.edu', 'state': 'CO'},
    {'name': 'Arizona State University', 'short': 'asu', 'domain': 'asu.edu', 'state': 'AZ'},

    # Tier 5: Additional research universities
    {'name': 'Brown University', 'short': 'brown', 'domain': 'brown.edu', 'state': 'RI'},
    {'name': 'Dartmouth College', 'short': 'dartmouth', 'domain': 'dartmouth.edu', 'state': 'NH'},
    {'name': 'Washington University in St Louis', 'short': 'wustl', 'domain': 'wustl.edu', 'state': 'MO'},
    {'name': 'Johns Hopkins University', 'short': 'jhu', 'domain': 'jhu.edu', 'state': 'MD'},
    {'name': 'California Institute of Technology', 'short': 'caltech', 'domain': 'caltech.edu', 'state': 'CA'},
    {'name': 'University of Pittsburgh', 'short': 'pitt', 'domain': 'pitt.edu', 'state': 'PA'},
    {'name': 'Rutgers University', 'short': 'rutgers', 'domain': 'rutgers.edu', 'state': 'NJ'},
    {'name': 'Virginia Tech', 'short': 'vt', 'domain': 'vt.edu', 'state': 'VA'},
    {'name': 'North Carolina State University', 'short': 'ncsu', 'domain': 'ncsu.edu', 'state': 'NC'},
    {'name': 'University of Arizona', 'short': 'arizona', 'domain': 'arizona.edu', 'state': 'AZ'},

    # Tier 6: More state flagships and research universities (51-70)
    {'name': 'Texas A&M University', 'short': 'tamu', 'domain': 'tamu.edu', 'state': 'TX'},
    {'name': 'University of Iowa', 'short': 'uiowa', 'domain': 'uiowa.edu', 'state': 'IA'},
    {'name': 'Indiana University', 'short': 'indiana', 'domain': 'indiana.edu', 'state': 'IN'},
    {'name': 'Michigan State University', 'short': 'msu', 'domain': 'msu.edu', 'state': 'MI'},
    {'name': 'University of Massachusetts Amherst', 'short': 'umass', 'domain': 'umass.edu', 'state': 'MA'},
    {'name': 'University of Delaware', 'short': 'udel', 'domain': 'udel.edu', 'state': 'DE'},
    {'name': 'University of Connecticut', 'short': 'uconn', 'domain': 'uconn.edu', 'state': 'CT'},
    {'name': 'Case Western Reserve University', 'short': 'case', 'domain': 'case.edu', 'state': 'OH'},
    {'name': 'Rensselaer Polytechnic Institute', 'short': 'rpi', 'domain': 'rpi.edu', 'state': 'NY'},
    {'name': 'Worcester Polytechnic Institute', 'short': 'wpi', 'domain': 'wpi.edu', 'state': 'MA'},
    {'name': 'University of Rochester', 'short': 'rochester', 'domain': 'rochester.edu', 'state': 'NY'},
    {'name': 'Northeastern University', 'short': 'northeastern', 'domain': 'northeastern.edu', 'state': 'MA'},
    {'name': 'Tufts University', 'short': 'tufts', 'domain': 'tufts.edu', 'state': 'MA'},
    {'name': 'Lehigh University', 'short': 'lehigh', 'domain': 'lehigh.edu', 'state': 'PA'},
    {'name': 'Syracuse University', 'short': 'syracuse', 'domain': 'syracuse.edu', 'state': 'NY'},
    {'name': 'University of Notre Dame', 'short': 'nd', 'domain': 'nd.edu', 'state': 'IN'},
    {'name': 'Georgetown University', 'short': 'georgetown', 'domain': 'georgetown.edu', 'state': 'DC'},
    {'name': 'University of California Riverside', 'short': 'ucr', 'domain': 'ucr.edu', 'state': 'CA'},
    {'name': 'University of Utah', 'short': 'utah', 'domain': 'utah.edu', 'state': 'UT'},
    {'name': 'University of Oregon', 'short': 'uoregon', 'domain': 'uoregon.edu', 'state': 'OR'},

    # Tier 7: Additional universities (71-100)
    {'name': 'Colorado State University', 'short': 'colostate', 'domain': 'colostate.edu', 'state': 'CO'},
    {'name': 'University of South Carolina', 'short': 'sc', 'domain': 'sc.edu', 'state': 'SC'},
    {'name': 'University of Tennessee', 'short': 'utk', 'domain': 'utk.edu', 'state': 'TN'},
    {'name': 'Iowa State University', 'short': 'iastate', 'domain': 'iastate.edu', 'state': 'IA'},
    {'name': 'University of Nebraska', 'short': 'unl', 'domain': 'unl.edu', 'state': 'NE'},
    {'name': 'University of Kansas', 'short': 'ku', 'domain': 'ku.edu', 'state': 'KS'},
    {'name': 'University of Missouri', 'short': 'missouri', 'domain': 'missouri.edu', 'state': 'MO'},
    {'name': 'University of Oklahoma', 'short': 'ou', 'domain': 'ou.edu', 'state': 'OK'},
    {'name': 'University of Alabama', 'short': 'ua', 'domain': 'ua.edu', 'state': 'AL'},
    {'name': 'Auburn University', 'short': 'auburn', 'domain': 'auburn.edu', 'state': 'AL'},
    {'name': 'Clemson University', 'short': 'clemson', 'domain': 'clemson.edu', 'state': 'SC'},
    {'name': 'University of Georgia', 'short': 'uga', 'domain': 'uga.edu', 'state': 'GA'},
    {'name': 'University of Kentucky', 'short': 'uky', 'domain': 'uky.edu', 'state': 'KY'},
    {'name': 'Louisiana State University', 'short': 'lsu', 'domain': 'lsu.edu', 'state': 'LA'},
    {'name': 'University of Arkansas', 'short': 'uark', 'domain': 'uark.edu', 'state': 'AR'},
    {'name': 'University of New Mexico', 'short': 'unm', 'domain': 'unm.edu', 'state': 'NM'},
    {'name': 'University of Nevada Reno', 'short': 'unr', 'domain': 'unr.edu', 'state': 'NV'},
    {'name': 'Oregon State University', 'short': 'oregonstate', 'domain': 'oregonstate.edu', 'state': 'OR'},
    {'name': 'Washington State University', 'short': 'wsu', 'domain': 'wsu.edu', 'state': 'WA'},
    {'name': 'University of Idaho', 'short': 'uidaho', 'domain': 'uidaho.edu', 'state': 'ID'},
    {'name': 'Montana State University', 'short': 'montana', 'domain': 'montana.edu', 'state': 'MT'},
    {'name': 'University of Wyoming', 'short': 'uwyo', 'domain': 'uwyo.edu', 'state': 'WY'},
    {'name': 'University of Vermont', 'short': 'uvm', 'domain': 'uvm.edu', 'state': 'VT'},
    {'name': 'University of Maine', 'short': 'umaine', 'domain': 'umaine.edu', 'state': 'ME'},
    {'name': 'University of New Hampshire', 'short': 'unh', 'domain': 'unh.edu', 'state': 'NH'},
    {'name': 'University of Rhode Island', 'short': 'uri', 'domain': 'uri.edu', 'state': 'RI'},
    {'name': 'Drexel University', 'short': 'drexel', 'domain': 'drexel.edu', 'state': 'PA'},
    {'name': 'Stevens Institute of Technology', 'short': 'stevens', 'domain': 'stevens.edu', 'state': 'NJ'},
    {'name': 'Illinois Institute of Technology', 'short': 'iit', 'domain': 'iit.edu', 'state': 'IL'},
    {'name': 'Santa Clara University', 'short': 'scu', 'domain': 'scu.edu', 'state': 'CA'},
]

# Common accelerator/incubator name patterns
ACCELERATOR_PATTERNS = [
    '{short} accelerator',
    '{short} incubator',
    '{short} venture lab',
    '{short} innovation',
    '{short} entrepreneurship',
    '{short} startup',
    '{name} accelerator',
    '{name} incubator',
    '{name} innovation lab',
    '{name} venture lab',
    '{name} startup studio',
]

# Common URL patterns to check
URL_PATTERNS = [
    'https://innovation.{domain}',
    'https://ventures.{domain}',
    'https://startup.{domain}',
    'https://accelerator.{domain}',
    'https://incubator.{domain}',
    'https://entrepreneurship.{domain}',
    'https://{short}startups.com',
    'https://www.{domain}/innovation',
    'https://www.{domain}/ventures',
    'https://www.{domain}/entrepreneurship',
]

# Known university accelerators (for validation)
KNOWN_ACCELERATORS = {
    'berkeley': {
        'name': 'Berkeley SkyDeck',
        'url': 'https://skydeck.berkeley.edu',
        'portfolio_url': 'https://skydeck.berkeley.edu/portfolio',
        'has_api': True,
        'api_type': 'Algolia'
    },
    'stanford': {
        'name': 'StartX',
        'url': 'https://startx.com',
        'portfolio_url': 'https://startx.com/companies',
        'has_api': False,
    },
    'mit': {
        'name': 'MIT Sandbox',
        'url': 'https://innovation.mit.edu/sandbox',
        'portfolio_url': None,
        'has_api': False,
    },
    'columbia': {
        'name': 'Columbia Startup Lab',
        'url': 'https://entrepreneurship.columbia.edu/startup-lab',
        'portfolio_url': None,
        'has_api': False,
    },
    'upenn': {
        'name': 'Penn Wharton Entrepreneurship',
        'url': 'https://entrepreneurship.wharton.upenn.edu',
        'portfolio_url': None,
        'has_api': False,
    },
}
