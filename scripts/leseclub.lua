--[[
Leseclub management
]]--

local R = {}

function R.borrow(book, person, weeks)
    data = ui.get_data{book='int', person='int'}
    if storage.pending_borrows[book] then
        ui.alert('book_already_borrowed')
        return
    end
    Borrow:new(data.book, data.person, weeks)
    storage.pending_borrows[data.book] = true
end

function R.restitute(book, person, points)
    if not buchschloss.storage.pending_borrows[book] then
        ui.alert('book_not_borrowed')
    end
    local ret = Borrow:restitute(book, person)
    storage.read_books[person] = (storage.read_books[person] or 0) + points
    ui.alert(ret)
end

local function get_results()
    local r = {}
    for k, v in pairs(storage.read_books) do
        r[Person[k].__str__] = v
    end
    ui.display(r)
end

local function start_leseclub()
    storage.pending_borrows = {}
    storage.read_books = {}
end

local function end_leseclub()
    if not ui.ask('really_end_leseclub') then
        return
    end
    storage.pending_borrows = nil
    storage.read_books = nil
end

if storage.pending_borrows and storage.read_books then
    R.end_leseclub = end_leseclub
    R.get_results = get_results
else
    R.start_leseclub = start_leseclub
end

return R
