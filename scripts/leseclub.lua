--[[
Leseclub management
]]--
-- TODO: add some kind of error handling

local borrow_weeks = 2 -- TODO: provide config access

local storage = buchschloss.get_storage()

function borrow()
    local data = ui.get_data{book='int', person='int'}
    data.weeks = borrow_weeks
    Borrow:new(data)
end

function restitute()
    local data = ui.get_data{book='int', person='int', points='int'}
    local ret = Borrow:restitute{book=data.book, person=data.person}
    storage.read_books[person] = (storage.read_books[person] or 0) + data.points
    buchschloss.set_storage(storage)
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
    buchschloss.set_storage(storage)
    ui.alert('leseclub_started')
end

function end_leseclub()
    if not ui.ask('really_end_leseclub') then
        return
    end
    storage.pending_borrows = nil
    storage.read_books = nil
    buchschloss.set_storage(storage)
    ui.alert('leseclub_ended')
end

ui.register_action('borrow', borrow)
ui.register_action('restitute', restitute)
if storage.pending_borrows and storage.read_books then
    ui.register_action('end_leseclub', end_leseclub)
    ui.register_action('get_results', get_results)
else if not (storage.pending_borrows or storage.read_books) then
    ui.register_action('start_leseclub', start_leseclub)
else
    error('storage corrupt')
end end
