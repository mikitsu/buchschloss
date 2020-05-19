--[[
Leseclub management
]]--
-- TODO: add some kind off error handling

local borrow_weeks = 2 -- TODO: provide config access

local R = {}

function borrow()
    local data = ui.get_data{book='int', person='int'}
    Borrow:new(data.book, data.person, borrow_weeks)
end

function restitute()
    local data = ui.get_data{book='int', person='int', points='int'}
    local ret = Borrow:restitute(book, person)
    storage.read_books[person] = (storage.read_books[person] or 0) + points
    ui.alert(ret)
end

function get_results()
    local r = {}
    for k, v in pairs(storage.read_books) do
        r[Person[k].__str__] = v
    end
    ui.display(r)
end

function start_leseclub()
    storage.pending_borrows = {}
    storage.read_books = {}
end

function end_leseclub()
    if not ui.ask('really_end_leseclub') then
        return
    end
    storage.pending_borrows = nil
    storage.read_books = nil
end

ui.register_action('borrow', borrow)
ui.register_action('restitute', restitute)
ui.register_action('get_results', get_results)
if storage.pending_borrows and storage.read_books then
    ui.register_action('end_leseclub', end_leseclub)
else if not (storage.pending_borrows or storage.read_books) then
    ui.register_action('start_leseclub', start_leseclub)
else
    error('storage corrupt')
end
