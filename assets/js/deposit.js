var msg = document.getElementById('depo_msg')


document.getElementById('depoForm').addEventListener('submit', function(e) {
    e.preventDefault()
    msg.innerHTML = ""
    if (document.getElementById('depo_amount_in_usd').value > 1000) {
        msg.innerHTML = "Max Deposit exceeded"
    } else if (document.getElementById('depo_amount_in_usd').value < 5) {
        msg.innerHTML = "Min Deposit Not exceeded"
    } else {
        document.getElementById('depoForm').submit();
        //makePayment()
    }

})












var local_currency = document.getElementById('user_l_currency').value;
var amount = document.getElementById('amount');
var amount_in_usd = document.getElementById('amount_in_usd');
var resultTo = 'USD'

const api = "https://api.exchangerate-api.com/v4/latest/USD";



function displayResults(currency) {
    //console.log(currency)
    let fromRate = currency.rates[local_currency];
    let toRate = currency.rates[resultTo];
    //console.log(fromRate, toRate)

    amount_in_usd.innerHTML = ((toRate / fromRate) * document.getElementById('amount').value).toFixed(2);
    document.getElementById('depo_amount_in_usd').value = ((toRate / fromRate) * document.getElementById('amount').value).toFixed(2);;


}

function getResults() {
    fetch(`${api}`)
        .then(currency => {
            return currency.json();
        }).then(displayResults);
}

amount.addEventListener('keyup', getResults)