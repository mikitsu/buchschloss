--[[
Leseclub management
]]--

local borrow_weeks = tonumber(config['borrow weeks'])
if borrow_weeks == nil then
    ui.alert('missing_config_{}', 'borrow weeks')
    return {}
end
local lc_library_name = config['library name'] or 'leseclub'
local manage_level = config['management level'] or 3

local storage = buchschloss.get_storage()


local function search_book(cond)
    return Book{
        {cond, 'and', {'is_active', 'eq', true}},
        'and', {'library.name', 'eq', lc_library_name},
    }
end

local function check_leseclub_active(wanted_active)
    -- no toboolean()?
    local is_active = storage.read_books and true or false
    if wanted_active == is_active then
        return false
    else
        if is_active then
            ui.alert('leseclub_active')
        else
            ui.alert('leseclub_not_active')
        end
        return true
    end
end

local function borrow()
    if check_leseclub_active(true) then return end
    local data = ui.get_data{
        {'book', 'choices', search_book{'not', {'exists', {'borrow.is_back', 'eq', false}}}},
        {'person', 'choices', Person{'libraries.name', 'eq', lc_library_name}},
    }
    if not data then return end
    data.weeks = borrow_weeks
    Borrow:new(data)
end

local function restitute()
    if check_leseclub_active(true) then return end
    local data = ui.get_data{
        {'book', 'choices', search_book{'borrow.is_back', 'eq', false}},
        {'points', 'int'},
    }
    if not data then return end
    local book = Book[data.book]
    local person = tostring(book.borrow.person.id)
    buchschloss.Borrow.edit{book.borrow, is_back=true}
    local new_points = (storage.read_books[person] or 0) + data.points
    storage.read_books[person] = new_points
    buchschloss.set_storage(storage)
end

local function get_results()
    if check_leseclub_active(true) then return end
    local r = {}
    for k, v in pairs(storage.read_books) do
        r[Person[k].__str__] = v
    end
    ui.display(r)
end

local function start_leseclub()
    if check_level(manage_level) then return end
    if check_leseclub_active(false) then return end
    storage.read_books = {}
    buchschloss.set_storage(storage)
    ui.alert('leseclub_started')
end

local function end_leseclub()
    if check_level(manage_level) then return end
    if check_leseclub_active(true) then return end
    if not ui.ask('really_end_leseclub') then
        return
    end
    storage.read_books = nil
    buchschloss.set_storage(storage)
    ui.alert('leseclub_ended')
end


return {
    start = start_leseclub,
    ['end'] = end_leseclub,
    get_results = get_results,
    borrow = borrow,
    restitute = restitute,
}
