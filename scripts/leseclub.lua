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

local function check_book_in_lc_library(book)
    if Book[book].library.name == lc_library_name then
        return false
    else
        ui.alert('book_not_in_leseclub_library')
        return true
    end
end

local function borrow()
    if check_leseclub_active(true) then return end
    local data = ui.get_data{book='int', person='int'}
    if not data then return end
    if check_book_in_lc_library(data.book) then return end
    data.weeks = borrow_weeks
    Borrow:new(data)
end

local function restitute()
    if check_leseclub_active(true) then return end
    local data = ui.get_data{book='int', points='int'}
    if not data then return end
    if check_book_in_lc_library(data.book) then return end
    local ret = buchschloss.Borrow.edit{buchschloss.Book.view_ns(data.book), is_back=false}
    local new_points = (storage.read_books[tostring(person)] or 0) + data.points
    storage.read_books[tostring(person)] = new_points
    buchschloss.set_storage(storage)
    ui.alert('restitute_success_{}', ret)
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
