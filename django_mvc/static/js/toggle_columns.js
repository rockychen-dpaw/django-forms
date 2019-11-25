var ToggleTableColumn =  function(key,toggleButtons,table,store) {
    this.key = window.location.pathname + "." + key
    this.toggleButtons = toggleButtons
    this.table = table
    if (store === false) {
        this.store = null
    } else {
        this.store = store || localStorage;
    }
    this.toggleableColumns = null
    this.toggledColumns = null
    this.defaultToggledColumns = null

}

ToggleTableColumn.prototype.init = function() {
    this.toggleButtons = $(this.toggleButtons)
    this.table = $(this.table)
    //get all toggleable columns
    var vm = this
    this.toggleableColumns = []
    this.defaultToggledColumns = []
    //get all toggleable columns
    //get default toggled columns as toggled columns
    $.each(this.toggleButtons,function(index,button) {
        button = $(button)
        vm.toggleableColumns.push(button.attr("data-class"))
        if (button.hasClass('btn-info')) {
            vm.defaultToggledColumns.push(button.attr("data-class"))
        }
        //attach event listener
        button.click(function(env){
            vm.toggleColumn($(env.target).attr("data-class") )
        })
    })
    //get toggled columns
    var state = (this.store === null)?null:this.store.getItem(this.key)
    if (state) {
        //get toggled columns from offline storage
        this.toggledColumns = JSON.parse(state)
        //change the column status
        $.each(this.toggleableColumns,function(index,column){
            if (vm.toggledColumns.indexOf(column) >= 0) {
                //should show
                if (vm.defaultToggledColumns.indexOf(column) >= 0) {
                    //already show, do nothing
                } else {
                    //hide by default, show it
                    vm.toggleColumn(column,true)
                }
            } else {
                //should hide
                if (vm.defaultToggledColumns.indexOf(column) >= 0) {
                    //show by default, hide it
                    vm.toggleColumn(column,false)
                } else {
                    //hide by default, do nothing
                }
            }
        })
    } else {
        vm.toggledColumns = vm.defaultToggledColumns
    }
}

ToggleTableColumn.prototype.toggleColumn = function(column,show) {
    if (show === null || show === undefined) {
        show = !(this.toggledColumns.indexOf(column) >= 0)
    }
    //show or hide the column in the table
    isShow = !this.table.find("th." + column).hasClass("hide")
    if (show === isShow ){
        //already show or hiden ,do nothing
    } else {
        this.table.find("th." + column).toggleClass("hide")
        this.table.find("td." + column).toggleClass("hide")
    }
    //add btninfo to button
    var button = this.toggleButtons.filter("#toggle-" + column)
    if (button) {
        if (show) {
            if (!button.hasClass("btn-info")) {
                button.addClass("btn-info")
            }
        } else {
            if (button.hasClass("btn-info")) {
                button.removeClass("btn-info")
            }
        }
    }
    //add or remove the column from toggled columns
    save = false
    if (show) {
        if (this.toggledColumns.indexOf(column) < 0) {
            //column is not in toggled columns
            this.toggledColumns.push(column)
            save = true
        }
    } else {
        var pos = this.toggledColumns.indexOf(column)
        if (pos >= 0) {
            //column is in toggled columns
            this.toggledColumns.splice(pos,1)
            save = true
        }
    }
    //save the toggled columns into offline storage if changed
    if (this.store && save) {
        this.store.setItem(this.key,JSON.stringify(this.toggledColumns))
    }

}
    
