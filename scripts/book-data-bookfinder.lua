--[[
Read book data from bookfinder.com

Data is passed via a horrible abuse of the ui interface
]]--

local isbn = math.floor(ui.get_data{isbn='int'}['isbn'])
local r = {}
-- Yes, these shouldn't be in config but transformed with get_name
-- Sadly, the UI interface is used for data passing here
local translations = config['language translations'] or {}

-- We could use https://www.bookfinder.com/book/{isbn}, but this is faster (doesn't sort)
local attribs = requests.get(
    'https://www.bookfinder.com/search/?lang=any&isbn='
    .. isbn .. '&classic=on&st=sr&ac=qr',
    'html'
).select_one('div.attributes')

for key, selector in pairs({author='author', title='name', publisher='publisher', language='inLanguage'}) do
    local field = attribs.select_one('span[itemprop="' .. selector .. '"]')
    if field ~= nil then
        r[key] = field.text
    end
end

-- bookfinder includes year with the publisher
if r.publisher ~= nil then
    r.publisher, r.year = string.match(r['publisher'], '(.-), (%d+)')
end
r.language = translations[r.language] or r.language

ui.display(r)
