//requirements
//work with listselector.html
//list table id must be [model]_result_list
//selector column head id must be [model]_selector_header
//selector column name must be 'selectedpks'
//other html element from listselector.html
//  total selected count : total_[model]_selected
//  the element to indicate all selected : all_[model]_selected
//  the element to select all: select_all_[model]
//  the element to clear selection: clear_[model]_selection
//  the element to send 'select all' flag to server: clear_[model]_select_all
var ListSelector = function(model,page_count,total_count,selected,select_all) {
    this.model = model;
    this.page_count = page_count;
    this.total_count = total_count;
    this.table = $("#"+ model + "_result_list")
    this.selector_header =  this.table.find("#" + model + "_selector_header")
    this.column_selector = this.table.find("input[name=selectedpks]")

    this.total_selected_count = $("#total_" + model + "_selected_count")
    this.total_selected = $("#total_" + model + "_selected")
    if (total_count > page_count) {
        this.all_selected = $("#all_" + model + "_selected")
        this.select_all_button = $("#select_all_" + model)
        this.select_all_field = $("#" + model + "_select_all")
        this.clean_selection = $("#clean_" + model + "_selection")
    }
    this.selected = 0
    if (select_all) {
        this.select(true,this.page_count);
        this.select_all();
    } else if (selected > 0) {
        this.select(true,selected)
    }
}


ListSelector.prototype.toggle_page_selection = function(checked) {
    if (checked !== undefined && checked !== null) {
        this.selector_header.prop('checked',checked)
    }
    if (this.selector_header.prop('checked')) {
        this.column_selector.prop('checked',true)
        this.selected = this.page_count
        if (this.total_count > this.page_count) {
            this.select_all_button.show()
        }
    } else {
        this.column_selector.prop('checked',false)
        this.selected = 0
        if (this.total_count > this.page_count) {
            this.select_all_button.hide()
            this.clean_selection.hide()
            this.all_selected.hide()
            this.total_selected.show()
            this.select_all_field.prop("disabled",true)
        }
    }
    this.total_selected_count.html(this.selected)
}

ListSelector.prototype.select_all = function() {
    this.selected = this.total_count
    this.total_selected_count.html(this.selected)

    this.column_selector.prop('checked',true)
    this.selector_header.prop('checked',true)
    if (this.total_count > this.page_count) {
        this.all_selected.show()
        this.total_selected.hide()
        this.select_all_button.hide()
        this.select_all_field.prop("disabled",false)
        this.clean_selection.show()
    }
}

ListSelector.prototype.select = function(checked,count) {
    count = count || 1
    if (checked) {
        this.selected += count
        if (this.selected == this.page_count) {
            this.selector_header.prop('checked',true)
        }
    } else {
        if (this.selected == this.total_count) {
            this.selected = this.page_count - count
            this.selector_header.prop('checked',false)
        } else if (this.selected == this.page_count) {
            this.selected -= count
            this.selector_header.prop('checked',false)
        } else {
            this.selected -= count
        }
    }

    this.total_selected_count.html(this.selected)

    if (this.total_count > this.page_count) {
        if (this.selected == this.page_count) {
            this.select_all_button.show()
        } else {
            this.select_all_button.hide()
        }
        this.all_selected.hide()
        this.total_selected.show()
        this.select_all_field.prop("disabled",true)
        this.clean_selection.hide()
    }

}

ListSelector.prototype.clean = function() {
    this.selected = 0
    this.total_selected_count.html(this.selected)

    this.column_selector.prop('checked',false)
    this.selector_header.prop('checked',false)
    if (this.total_count > this.page_count) {
        this.all_selected.hide()
        this.total_selected.show()
        this.select_all_button.hide()
        this.select_all_field.prop("disabled",true)
        this.clean_selection.hide()
    }
}


