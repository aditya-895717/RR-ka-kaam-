from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, EmailOTP,
    HospitalProfile, HospitalDepartment, HospitalStaffProfile,
    LaundryProfile, LaundryWorkerProfile, DeliveryProfile,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role', 'is_onboarded', 'is_active', 'date_joined')
    list_filter = ('role', 'is_onboarded', 'is_active', 'is_staff')
    search_fields = ('email', 'full_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('full_name', 'phone_number')}),
        ('Role & Status', {'fields': ('role', 'is_onboarded')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'password1', 'password2'),
        }),
    )
    readonly_fields = ('date_joined', 'last_login')


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'otp_code', 'created_at', 'is_used')
    list_filter = ('is_used',)
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)


class HospitalDepartmentInline(admin.TabularInline):
    model = HospitalDepartment
    extra = 1
    fields = ('department_name',)


@admin.register(HospitalProfile)
class HospitalProfileAdmin(admin.ModelAdmin):
    list_display = ('hospital_name', 'city', 'area', 'phone_number', 'created_at')
    list_filter = ('city',)
    search_fields = ('hospital_name', 'city', 'area', 'user__email')
    readonly_fields = ('created_at',)
    inlines = [HospitalDepartmentInline]


@admin.register(HospitalDepartment)
class HospitalDepartmentAdmin(admin.ModelAdmin):
    list_display = ('department_name', 'hospital', 'created_at')
    list_filter = ('hospital',)
    search_fields = ('department_name', 'hospital__hospital_name')
    readonly_fields = ('created_at',)


@admin.register(HospitalStaffProfile)
class HospitalStaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'hospital', 'department', 'phone_number', 'created_at')
    list_filter = ('hospital',)
    search_fields = ('user__email', 'hospital__hospital_name')
    readonly_fields = ('created_at',)


@admin.register(LaundryProfile)
class LaundryProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'city', 'area', 'phone_number', 'price_per_item', 'is_available', 'created_at')
    list_filter = ('city', 'is_available')
    search_fields = ('business_name', 'city', 'area', 'user__email')
    readonly_fields = ('created_at',)


@admin.register(LaundryWorkerProfile)
class LaundryWorkerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'laundry', 'phone_number', 'created_at')
    list_filter = ('laundry',)
    search_fields = ('user__email', 'laundry__business_name')
    readonly_fields = ('created_at',)


@admin.register(DeliveryProfile)
class DeliveryProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'city', 'area', 'vehicle_type', 'is_available', 'created_at')
    list_filter = ('city', 'vehicle_type', 'is_available')
    search_fields = ('user__email', 'city', 'area')
    readonly_fields = ('created_at',)
