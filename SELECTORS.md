# Iowa Realty Selectors Documentation

Generated from exploration on 2025-12-17

## Page Structure

- **Properties per page**: 100
- **Property card element**: `<article class="prop-card" id="property_{id}">`

## Listing Page Selectors

### Property Cards
- **Container**: `article.prop-card` or `article`
- **Property ID**: Extract from `id` attribute (e.g., `id="property_117500519"` → `117500519`)

### Fields within each card

1. **Price**
   - Selector: `.price`
   - Example: `$92,900`
   - Parsing: Strip "$" and commas, convert to int

2. **Status**
   - Selector: `.status`
   - Example: `Active`, `Pending`, etc.
   - Additional: New listings have `<div class="banner"><span>New</span></div>`

3. **Address** (two h3 elements with class "address")
   - Selector: `h3.address`
   - First h3: Street address (e.g., "659 3rd Place")
   - Second h3: City, State, ZIP (e.g., "Mason City, IA 50401")
   - Parsing: Need to extract both and combine/split as needed

4. **Property Details** (in `ul.info` list)
   - Selector: `ul.info li`
   - li[0]: Property Type (e.g., "Single Family")
   - li[1]: Beds (e.g., "3 Beds")
   - li[2]: Baths (e.g., "2 Baths")
   - li[3]: Square Footage (e.g., "1,901 sqft")
   - Parsing:
     - Beds: Extract number before "Bed"
     - Baths: Extract number (including decimals like "2.5") before "Bath"
     - Sqft: Strip "sqft" and commas, convert to int

5. **Detail Page URL**
   - Pattern: `./details/{property_id}/{address-slug}`
   - Example: `./details/117500519/659-3rd-place-mason-city-ia-50401`
   - Full URL: `https://www.iowarealty.com/details/{property_id}/{address-slug}`
   - Construction: Can build from property ID and address, or find `a[href*="/details/"]` within card

## Pagination

- **Selector**: `.pagination` or `nav[aria-label*="page" i]`
- **Structure**: Shows page numbers (1, 2, 3, 4, 5, ...)
- **Navigation**: Can click on page numbers or use "Next" button if available
- **Total pages**: Extract from pagination controls (look for highest number)

## Detail Page (to be explored further)

**URL Pattern**: `https://www.iowarealty.com/details/{property_id}/{address-slug}`

Fields to extract on detail page:
- Full property description
- MLS number
- Year built
- Lot size
- Days on market
- Listing date
- Additional property details

## Sample Property Card HTML

```html
<article class="prop-card" id="property_117500519">
  <div class="image-area">
    <!-- Image and favorite button -->
  </div>
  <div class="text-area">
    <div class="price">$92,900</div>
    <div class="status active">Active</div>
    <h3 class="address">659 3rd Place</h3>
    <h3 class="address">Mason City, IA 50401</h3>
    <ul class="info">
      <li>Single Family</li>
      <li>3 Beds</li>
      <li>2 Baths</li>
      <li>1,901 sqft</li>
    </ul>
  </div>
</article>
```

## Parsing Helper Functions Needed

1. `_parse_price(text: str) -> int`: Strip "$", commas → int
2. `_parse_beds(text: str) -> int`: Extract number from "3 Beds"
3. `_parse_baths(text: str) -> float`: Extract number from "2.5 Baths"
4. `_parse_sqft(text: str) -> int`: Strip "sqft", commas → int
5. `_parse_address(addr1: str, addr2: str) -> dict`: Split city, state, zip
6. `_build_detail_url(property_id: str, address: str) -> str`: Construct detail URL
