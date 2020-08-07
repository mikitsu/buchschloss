--[[
    Check for late books
    Display late books
]]--

-- 86400 == 60*60*24 == seconds in a day
local interval = 86400 * (config.warn_days or 0)

local function get_books()
    -- REMINDER:
    -- (late) < [today] < (warn) < [today + x] < (OK)
    -- e.g. yesterday     tomorrow              next month
    local check = os.date('%Y-%m-%d', os.time() + interval)
    local late = Borrow{{'is_back','eq',false},
                         'and',{'return_date','lt',today}}
    local warn = Borrow{{{'is_back','eq',false},
                         'and',{'return_date','lt',check}},
                         'and',{'return_date','gt',today}}
    return reformat_borrows(late), reformat_borrows(warn)
end

local function reformat_borrows(borrows)
    local r = {}
    for k, v in pairs(borrows) do
        r[k] = {v.person, v.book, v.return_date}
    end
    return r
end

local function check()
    local late, warn = get_books()
    local msg = ''
    if #late > 0 then
        msg = msg .. ui.get_name('late_books_present') .. '\n'
    end
    if #warn > 0 then
        msg = msg .. ui.get_name('warn_books_present') .. '\n'
    end
    if #msg > 0 then
        ui.display(msg)
    end
end

local function show()
    local late, warn = get_books()
    ui.display{[ui.get_name('late')] = late, [ui.get_name('warn')] = warn}
end

return {
    check=check,
    show=show,
}
