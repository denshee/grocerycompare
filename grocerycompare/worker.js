export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        // Enable CORS for frontend
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Content-Type': 'application/json'
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { headers: corsHeaders });
        }

        // Extract Airtable table and query from URL
        // Example: /api/airtable/Listings?filterByFormula=...
        const path = url.pathname.replace('/api/airtable/', '');
        const airtableUrl = `https://api.airtable.com/v0/${env.AIRTABLE_BASE_ID}/${path}${url.search}`;

        const response = await fetch(airtableUrl, {
            headers: {
                'Authorization': `Bearer ${env.AIRTABLE_TOKEN}`
            }
        });

        const data = await response.json();
        return new Response(JSON.stringify(data), { headers: corsHeaders });
    }
};
