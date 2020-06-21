--[[
Leseclub management
]]--
-- TODO: add some kind of error handling

local borrow_weeks = tonumber(config['borrow weeks'])
if borrow_weeks == nil then
    error('missing configuration value "borrow weeks"')
end
local lc_library_name = config['library name'] or 'leseclub'

local storage = buchschloss.get_storage()


local function check_leseclub_active(wanted_active)
    local is_active
    if storage.pending_borrows and storage.read_books then
        is_active = true
    else if not (storage.pending_borrows or storage.read_books) then
        is_active = false
    else
        error('storage corrupt')
    end end
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
    if check_book_in_lc_library(data.book) then return end
    data.weeks = borrow_weeks
    Borrow:new(data)
end

local function restitute()
    if check_leseclub_active(true) then return end
    local data = ui.get_data{book='int', person='int', points='int'}
    if check_book_in_lc_library(data.book) then return end
    local person = data.person
    local ret = Borrow:restitute{book=data.book, person=person}
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
    if check_leseclub_active(false) then return end
    storage.pending_borrows = {}
    storage.read_books = {}
    buchschloss.set_storage(storage)
    ui.alert('leseclub_started')
end

local function end_leseclub()
    if check_leseclub_active(true) then return end
    if not ui.ask('really_end_leseclub') then
        return
    end
    storage.pending_borrows = nil
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
