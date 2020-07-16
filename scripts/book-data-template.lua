--[[
This is a template for book data scripts
Read book data from example.com

Data is passed via a horrible abuse of the ui interface
]]--

-- This is needed to not have a .0 at the end
local isbn = math.floor(ui.get_data{isbn='int'}['isbn'])
local r = {}

-- build the URL with the ISBN
local page = requests.get('https://example.com/some/path?isbn=' .. isbn, 'html')

-- somehow fill ``r`` here...
local title_element = page.select('div.example span[whatAmI="title"]')
if title_element ~= nil then
    r.title = title_element.text
end

ui.display(r)
