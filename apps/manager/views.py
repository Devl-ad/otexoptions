from django.shortcuts import render
from .decorator import manager_required
from django.db.models import Sum
from apps.account.models import User, KYCSubmission
from apps.dashboard.models import Transaction


@manager_required
def index(request):
    total_users = User.objects.filter(email_verified=True).count()
    total_deposit = (
        Transaction.objects.filter(
            transaction_type=Transaction.TransactionType.DEPOSIT,
            status=Transaction.Status.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    total_withdrawal = (
        Transaction.objects.filter(
            transaction_type=Transaction.TransactionType.WITHDRAWAL,
            status=Transaction.Status.COMPLETED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    total_deposit_count = Transaction.objects.filter(
        transaction_type=Transaction.TransactionType.DEPOSIT,
        status=Transaction.Status.COMPLETED,
    ).count()

    total_withdrawal_count = Transaction.objects.filter(
        transaction_type=Transaction.TransactionType.WITHDRAWAL,
        status=Transaction.Status.COMPLETED,
    ).count()

    total_pending_kyc = KYCSubmission.objects.filter(
        status=KYCSubmission.Status.PENDING
    ).count()

    pending_transactions = Transaction.objects.filter(
        status=Transaction.Status.PENDING
    )[:10]

    context = {
        "total_users": total_users,
        "total_deposit": total_deposit,
        "total_withdrawal": total_withdrawal,
        "total_deposit_count": total_deposit_count,
        "total_withdrawal_count": total_withdrawal_count,
        "total_pending_kyc": total_pending_kyc,
        "pending_transactions": pending_transactions,
    }
    return render(request, "manager/index.html", context)
