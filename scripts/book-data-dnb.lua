--[[
Read book data from the DNB

Data is passed via a horrible abuse of the ui interface
]]--

local function strip(s)
    return string.match(s, '^%s*(.-)%s*$')
end

local isbn = math.floor(ui.get_data{isbn='int'}['isbn'])

local page = requests.get(
    'https://portal.dnb.de/opac.htm?query=isbn%3D'
    .. isbn
    .. '&method=simpleSearch&cqlMode=true',
    'html'
)

local r = {concerned_people={}}

local data_table = page.select_one('#fullRecordTable')
if data_table == nil then
    -- see if we got multiple results
    local link_to_first = page.select_one('#recordLink_0')
    if link_to_first == nil then
        return
    end
    page = requests.get('https://portal.dnb.de' .. link_to_first.attrs.href, 'html')
    data_table = page.select_one('#fullRecordTable')
end

for _, tr in ipairs(data_table.select('tr')) do
    local td = tr.select('td')
    if #td == 2 then
        local key = strip(td[1].text)
        local value = strip(td[2].text)
        if key == 'Titel' then
            r['title'] = value
        elseif key == 'Person(en)' then
            for person, role in string.gmatch(value, '([%a %-]+, [%a %-]+) %(([%a %-]+)%)') do
                if role == 'Verfasser' then
                    r.author = person
                else
                    table.insert(r.concerned_people, role .. ': ' .. person)
                end
            end
        elseif key == 'Verlag' then
            r.publisher = string.match(value, '^.+%:%s*(.+)%s*$')
        elseif key == 'Zeitliche Einordnung' then
            r.year = tonumber(string.match(value, '%d%d%d%d'))
        elseif key == 'Sprache(n)' then
            r.language = string.match(value, '%a+')
        end
    end
end
r.concerned_people = table.concat(r.concerned_people, '; ')
ui.display(r)
