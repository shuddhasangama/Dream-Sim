# Signup sections and date preferences release

Built 18 November 2026. No database migration or new environment variable required.

## Behaviour
- Basics (name, DOB, gender, city) are required. Existing adult age and identity checks remain.
- Date preferences follows Basics; optional during signup.
- Remaining collapsible sections: Work & education, Background & family, Lifestyle, Health & accessibility.
- Choose up to three neighbourhoods from six in the selected city. Changing city clears the selection.
- After matching, Home prompts a review of date preferences. Saved choices are prefilled; the mobile calendar shows preferences before slots until reviewed for this pair/date cycle.
- Review saves budget, diet, cuisine and neighbourhoods. The next action opens availability, subject to existing calendar eligibility.
- Existing clients can still send the original alignment payload. This is a mobile review flow, not an additional backend admission restriction.
- With booking coordination enabled in a supported market, date-area choices also update the pair booking preferences atomically. Existing booking requirements and provider connection states remain.
- Catalogue presence does not enable signup or establish restaurant availability. Bengaluru (stored as Bangalore), Delhi and Mumbai remain enabled. The remaining eight stay disabled in launch_cities.py.

## Curated launch catalogue
These are practical dining-area shortlists, not an official ranking or confirmed restaurant inventory. The UI catalogue has no fabricated geographic coordinates. Existing Bengaluru booking coordinates remain in booking_markets.json; expanding live restaurant search to other cities still requires configured and validated booking markets.

| City | Six choices |
| --- | --- |
| Bangalore | Indiranagar, Koramangala, MG Road, Jayanagar, HSR Layout, Whitefield |
| Delhi | Connaught Place, Hauz Khas, Saket, Greater Kailash, Defence Colony, Janakpuri |
| Mumbai | Bandra West, Lower Parel, Bandra Kurla Complex, Powai, Andheri West, Malad West |
| Hyderabad | Jubilee Hills, Banjara Hills, Gachibowli, Madhapur, Kondapur, Himayatnagar |
| Chennai | Nungambakkam, Adyar, Anna Nagar, T Nagar, Velachery, Alwarpet |
| Kolkata | Park Street, Salt Lake, New Town, Ballygunge, Alipore, Southern Avenue |
| Pune | Koregaon Park, Kalyani Nagar, Viman Nagar, Baner, Aundh, Deccan Gymkhana |
| Ahmedabad | Bodakdev, Thaltej, Navrangpura, Prahlad Nagar, Satellite, Chandkheda |
| Jaipur | C Scheme, Malviya Nagar, Vaishali Nagar, Raja Park, Mansarovar, Bani Park |
| Chandigarh | Sector 7, Sector 8, Sector 9, Sector 17, Sector 26, Sector 35 |
| Kochi | Fort Kochi, Panampilly Nagar, Kakkanad, Edappally, Marine Drive, Vyttila |

## Research references
Shortlists use dining listings and geographic spread; listing availability can change.
- Delhi Tourism: https://delhitourism.gov.in/dt/delhi-delicacies.html
- District Mumbai: https://www.district.in/dining/mumbai/restaurants
- District Chennai: https://www.district.in/dining/chennai/restaurants
- District Ahmedabad: https://www.district.in/dining/ahmedabad/restaurants
- Pune: https://www.zomato.com/pune/kalyani-nagar-restaurants
- Jaipur: https://www.swiggy.com/city/jaipur/indian-dish-restaurants
- Chandigarh: https://www.swiggy.com/dineout/Chandigarh
- Kochi: https://www.swiggy.com/city/kochi

## Deployment
Use C:\DreamContractLocalBKP\ChatGPT\dhashu-employment-release (branch codex/employment-progress-release).
Commit only the files in this release, fetch origin and rebase onto origin/master, then push HEAD:master. If a conflict occurs, stop and resolve it before pushing; do not force push.
Wait for Railway Dream-Sim to report the new commit deployed. No shell migration, purge or seed command is needed.
Then build Android and iOS in Codemagic from master and distribute updated test builds. Installed mobile apps need the new build for these screens.

## Smoke checks
1. New signup: missing Basics is rejected; date preferences may be skipped.
2. Select Bengaluru: six areas, maximum three. Switch to Delhi: previous areas clear.
3. Save and reopen: same choices restored.
4. After matching: Home offers Review preferences, then Next: choose availability.
5. Verify both partners' booking-area overlap when booking coordination is enabled.
