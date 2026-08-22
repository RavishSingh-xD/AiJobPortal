/**
 * Static sub-domain / specialty suggestions for portal domain pickers.
 * Mirrors jobsniper/subdomain_suggestions.py (subset for UI hints).
 */

const SUBDOMAIN_BY_DOMAIN = {
  Engineering: [
    "Full Stack Development",
    "Backend Development",
    "Frontend Development",
    "Machine Learning / AI",
    "Data Engineering",
    "DevOps / Cloud Infrastructure",
    "Cybersecurity",
    "Mobile App Development",
    "Embedded Systems",
    "Civil Engineering",
    "Electrical Engineering",
    "Mechanical Engineering",
  ],
  Healthcare: [
    "Cardiology",
    "Neurology",
    "Orthopedics",
    "Pediatrics",
    "Dermatology",
    "General Surgery",
    "Psychiatry",
    "Radiology",
    "Internal Medicine",
    "ICU / Critical Care",
    "Pediatric Nursing",
  ],
  Business: [
    "Digital Marketing",
    "SEO / Content Marketing",
    "Brand Management",
    "B2B Sales",
    "Financial Analysis",
    "Corporate Finance",
    "Business Analysis",
    "Operations Management",
    "Product Management",
    "Corporate Tax",
    "Investment Banking",
  ],
};

export function getSubdomainSuggestions(domain) {
  if (!domain) return [];
  return SUBDOMAIN_BY_DOMAIN[domain] || [];
}

export const DOMAIN_SKILL_EXAMPLES = {
  Engineering: "e.g. Python, React, Machine Learning",
  Healthcare: "e.g. Cardiology, Nursing, Internal Medicine",
  Business: "e.g. Marketing, Sales, Corporate Finance",
};
