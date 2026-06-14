'use strict';


(function($) {


    $(document).ready(function() {

        setInterval(function() {
            var dt = new Date();
            var x1 = dt.toUTCString();
            document.getElementById("date-bar").innerHTML = x1;
        }, 1000)



    })





})(jQuery);


function showNotify(title, body, limit = 6000) {

    jQuery('.notify-title').text(`${title}`);
    jQuery('.notify-body').text(`${body}`);
    jQuery('.notify').addClass('active');
    setTimeout(function() {
        $('.notify').removeClass('active');

    }, limit)

}








function showMNotify(limit = 1000) {


    var notify = document.getElementById('nitifym');
    notify.classList.add('active')

    setTimeout(function() {
        notify.classList.remove('active')
    }, limit)

}