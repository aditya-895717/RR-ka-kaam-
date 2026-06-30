import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    HOSPITAL_HEAD = 'HOSPITAL_HEAD', 'Hospital Head'
    HOSPITAL_STAFF = 'HOSPITAL_STAFF', 'Hospital Staff'
    LAUNDRY_ADMIN = 'LAUNDRY_ADMIN', 'Laundry Admin'
    LAUNDRY_WORKER = 'LAUNDRY_WORKER', 'Laundry Worker'
    DELIVERY_PARTNER = 'DELIVERY_PARTNER', 'Delivery Partner'


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        if not extra_fields.get('is_staff'):
            raise ValueError('Superuser must have is_staff=True.')
        if not extra_fields.get('is_superuser'):
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, blank=True)
    is_onboarded = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split()[0] if self.full_name else self.email


class EmailOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otps')
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        expiry = self.created_at + timezone.timedelta(minutes=10)
        return not self.is_used and timezone.now() <= expiry

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'OTP for {self.user.email}'


# ─────────────────────────────────────────────
# Role-based profile models
# ─────────────────────────────────────────────

class HospitalProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='hospital_profile',
    )
    hospital_name = models.CharField(max_length=255)
    hospital_address = models.TextField()
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.hospital_name


class HospitalDepartment(models.Model):
    hospital = models.ForeignKey(
        HospitalProfile, on_delete=models.CASCADE, related_name='departments',
    )
    department_name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.department_name} — {self.hospital.hospital_name}'


class HospitalStaffProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='hospital_staff_profile',
    )
    hospital = models.ForeignKey(
        HospitalProfile, on_delete=models.CASCADE, related_name='staff',
    )
    department = models.ForeignKey(
        HospitalDepartment, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='staff',
    )
    phone_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} @ {self.hospital.hospital_name}'


class LaundryProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='laundry_profile',
    )
    business_name = models.CharField(max_length=255)
    address = models.TextField()
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    price_per_item = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.business_name


class LaundryWorkerProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='laundry_worker_profile',
    )
    laundry = models.ForeignKey(
        LaundryProfile, on_delete=models.CASCADE, related_name='workers',
    )
    phone_number = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} @ {self.laundry.business_name}'


class DeliveryProfile(models.Model):
    class VehicleType(models.TextChoices):
        BIKE = 'BIKE', 'Bike'
        AUTO = 'AUTO', 'Auto'
        VAN = 'VAN', 'Van'
        OTHER = 'OTHER', 'Other'

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='delivery_profile',
    )
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    vehicle_type = models.CharField(
        max_length=10, choices=VehicleType.choices, blank=True,
    )
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} ({self.city})'
