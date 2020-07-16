--[[
Read book data from bookfinder.com

Data is passed via a horrible abuse of the ui interface
]]--

local isbn = math.floor(ui.get_data{isbn='int'}['isbn'])
local r = {}
-- See note on usage below
local translations = {
    German='Deutsch',
    English='Englisch',
}

local page = requests.get('https://www.bookfinder.com/book/' .. isbn, 'html')

for key, selector in pairs({author='author', title='name', publisher='publisher', language='inLanguage'}) do
    local field = page.select_one('span[itemprop="' .. selector .. '"]')
    if field ~= nil then
        r[key] = field.text
    end
end

-- bookfinder includes year with the publisher
if r.publisher ~= nil then
    r.publisher, r.year = string.match(r['publisher'], '(.-), (%d+)')
end
-- Yes, these shouldn't be hardcoded but transformed with get_name
-- Sadly, the UI interface is used for data passing here
r.language = translations[r.language]

ui.display(r)
