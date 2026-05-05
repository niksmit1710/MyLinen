from django.db import models

# Create your models here.
class Shipment(models.Model):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE)
    status = models.CharField(max_length=50)
    tracking_id = models.CharField(max_length=100)
    estimated_delivery_date = models.DateField() 
